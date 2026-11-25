"""Add native, relative Excel links to the generated research workbook."""
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from locales import LANGUAGES, folders, label

SHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
WEB_HEADERS = {label(key, language) for key in ("url", "evidence_url") for language in LANGUAGES}
LOCAL_HEADERS = {label("local", language) for language in LANGUAGES}


def column_name(number):
    name = ""
    while number:
        number, position = divmod(number - 1, 26)
        name = chr(65 + position) + name
    return name


def target_for(header, value, root):
    if not value:
        return None
    if header in LOCAL_HEADERS:
        path = PurePosixPath(value)
        if (path.is_absolute() or not path.parts or path.parts[0] not in folders("originals")
                or ".." in path.parts or not (root / value).is_file()
                or not (root / value).resolve().is_relative_to((root / path.parts[0]).resolve())):
            raise ValueError(f"Broken attachment link: {value}")
        return quote(value, safe="/")
    if header in WEB_HEADERS:
        url = urlsplit(value)
        if url.scheme in {"https", "http"} and url.hostname and not url.username:
            return value
    return None


def add_links(workbook, sheets, root):
    replacement = workbook.with_name(workbook.name + ".links")
    output = {}
    ET.register_namespace("x", SHEET)
    ET.register_namespace("r", OFFICE_REL)
    ET.register_namespace("", PACKAGE_REL)
    with ZipFile(workbook) as source:
        names = set(source.namelist())
        for index, rows in enumerate(sheets.values(), 1):
            links = [(f"{column_name(col)}{row}", target)
                     for row, values in enumerate(rows[1:], 2)
                     for col, (header, value) in enumerate(zip(rows[0], values), 1)
                     if (target := target_for(header, value, root))]
            if not links:
                continue
            name = f"xl/worksheets/sheet{index}.xml"
            relname = f"xl/worksheets/_rels/sheet{index}.xml.rels"
            sheet = ET.fromstring(source.read(name))
            rels = (ET.fromstring(source.read(relname)) if relname in names
                    else ET.Element(f"{{{PACKAGE_REL}}}Relationships"))
            if sheet.find(f"{{{SHEET}}}hyperlinks") is not None:
                raise ValueError("Generated worksheet already contains hyperlinks")
            collection = ET.Element(f"{{{SHEET}}}hyperlinks")
            # Hyperlinks precede print/drawing/table records in worksheet schema order.
            before = {"printOptions", "pageMargins", "pageSetup", "headerFooter", "rowBreaks",
                      "colBreaks", "customProperties", "cellWatches", "ignoredErrors", "smartTags",
                      "drawing", "legacyDrawing", "legacyDrawingHF", "picture", "oleObjects",
                      "controls", "webPublishItems", "tableParts", "extLst"}
            position = next((i for i, child in enumerate(sheet)
                             if child.tag.rsplit("}", 1)[-1] in before), len(sheet))
            sheet.insert(position, collection)
            used = {r.attrib["Id"] for r in rels}
            for ref, target in links:
                identifier = f"ResearchLink{ref}"
                if identifier in used:
                    raise ValueError(f"Duplicate workbook relationship {identifier}")
                ET.SubElement(collection, f"{{{SHEET}}}hyperlink",
                              {"ref": ref, f"{{{OFFICE_REL}}}id": identifier})
                ET.SubElement(rels, f"{{{PACKAGE_REL}}}Relationship",
                              dict(Id=identifier, Type=OFFICE_REL + "/hyperlink",
                                   Target=target, TargetMode="External"))
            output[name] = ET.tostring(sheet, encoding="utf-8", xml_declaration=True)
            output[relname] = ET.tostring(rels, encoding="utf-8", xml_declaration=True)
        with ZipFile(replacement, "x") as dest:
            for entry in source.infolist():
                dest.writestr(entry, output.pop(entry.filename, None) or source.read(entry))
            for name, data in output.items():
                dest.writestr(name, data)
    replacement.replace(workbook)


def verify_links(workbook, sheets, root):
    """Check links in the serialized workbook in both directions."""
    listed = []
    with ZipFile(workbook) as archive:
        names = set(archive.namelist())
        for index, rows in enumerate(sheets.values(), 1):
            expected = {}
            for row, values in enumerate(rows[1:], 2):
                for column, (header, value) in enumerate(zip(rows[0], values), 1):
                    target = target_for(header, value, root)
                    if target:
                        expected[f"{column_name(column)}{row}"] = target
                        if header in LOCAL_HEADERS:
                            listed.append(value)
            worksheet = ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
            relpath = f"xl/worksheets/_rels/sheet{index}.xml.rels"
            relations = {r.get("Id"): r.get("Target") for r in ET.fromstring(archive.read(relpath))
                         if r.get("Type") == OFFICE_REL + "/hyperlink" and r.get("TargetMode") == "External"
                         } if relpath in names else {}
            links = worksheet.findall(f"{{{SHEET}}}hyperlinks/{{{SHEET}}}hyperlink")
            actual = {link.get("ref"): relations.get(link.get(f"{{{OFFICE_REL}}}id")) for link in links}
            if len(actual) != len(links) or actual != expected:
                raise ValueError(f"Worksheet {index} links differ from the catalogue")
    actual_files = {path.relative_to(root).as_posix() for name in folders("originals") for path in (root / name).rglob("*")
                    if path.is_file() and path.name != ".DS_Store"}
    if len(listed) != len(set(listed)) or set(listed) != actual_files:
        raise ValueError(f"Excel attachment links differ from actual files：{sorted(set(listed) ^ actual_files)}")
