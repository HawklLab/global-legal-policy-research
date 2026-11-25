"""Presentation labels. Persistent schemas use the keys below, never these labels."""
LANGUAGES = {"en", "zh-CN", "bilingual"}

LABELS = {
    "catalog": ("Catalogue", "资料目录"), "pending": ("Pending items", "待补与问题"),
    "sources": ("Sources", "检索网站"), "originals": ("Originals", "文献原文"),
    "records": ("Records", "后台记录"), "workbook": ("Catalogue", "资料总目录"),
    "summary": ("Research notes", "检索说明"),
    "id": ("Record ID", "资料编号"), "title": ("Original title", "原文标题"),
    "translation": ("Working title translation", "辅助译名"), "creator": ("Original author or publisher", "原文作者或机构"),
    "date": ("Publication date", "发布日期"), "category": ("Category", "主要分类"),
    "themes": ("Themes", "研究主题"), "settings": ("Dimensions", "研究维度"),
    "type": ("Document type", "文献类型"), "number": ("Legal or document number", "法律或文献编号"),
    "doi": ("DOI", "DOI"), "language": ("Document language", "文献语种"),
    "url": ("Source URL", "原始网址"), "local": ("Local file", "本地原文链接"),
    "access": ("Full-text status", "全文状态"), "verification": ("Source verification", "来源核验状态"),
    "retrieved": ("Retrieved on", "检索日期"), "remarks": ("Remarks", "备注"),
    "reason": ("Acquisition or verification issue", "获取或核验问题"), "institution": ("Institution", "机构"),
    "authority": ("Authority", "来源性质"), "limitations": ("Limitations", "覆盖限制"),
    "checked": ("Verified on", "核验日期"), "evidence_url": ("Evidence URL", "核验依据链接"),
    "saved_pdf": ("Saved PDF", "已保存PDF"), "saved_html": ("Saved HTML", "已保存HTML"),
    "saved_other": ("Saved other format", "已保存其他格式"), "online_full": ("Full text online", "可在线阅读全文"),
    "partial": ("Saved partial text", "已保存部分正文"), "abstract": ("Abstract or metadata only", "仅有摘要"),
    "subscription": ("Institutional subscription required", "需机构订阅"),
    "archive_lead": ("Archival lead only", "仅有档案线索"), "unverified": ("Needs verification", "待核实"),
    "verified": ("Verified", "已核验"), "pending_status": ("Pending", "待核验"),
    "access_limited": ("Access limited", "访问受限"),
    "legislation": ("Legislation", "法律法规"), "amendment": ("Amendment", "修正法令"),
    "bill": ("Bill", "法案"), "debate": ("Debate", "审议"), "policy": ("Policy", "政策"),
    "advocacy": ("Advocacy", "倡导"), "consultation": ("Consultation", "征询"),
    "court-decision": ("Court decision", "判决"), "evaluation": ("Evaluation", "评估"),
    "journal-article": ("Journal article", "期刊论文"), "report": ("Report", "报告"),
    "committee-report": ("Committee report", "委员会报告"), "preparatory-report": ("Preparatory report", "立法准备文件"),
    "campaign-history": ("Campaign history", "倡导史"), "campaign-material": ("Campaign material", "倡导材料"),
    "campaign-proposal": ("Campaign proposal", "倡导提案"), "country-report": ("Country report", "国别报告"),
    "international-record": ("International record", "国际组织记录"), "international-report": ("International report", "国际组织报告"),
    "parliamentary-decision": ("Parliamentary decision", "议会决定"),
    "book-chapter": ("Book chapter", "书籍章节"), "research-report": ("Research report", "研究报告"),
    "thesis": ("Thesis", "学位论文"), "other": ("Other", "其他"),
    "gaps": ("Coverage gaps", "检索覆盖缺口"), "topic": ("Topic", "主题"), "scope": ("Scope", "范围"),
    "cutoff": ("Cutoff", "截止日期"), "search_languages": ("Search languages", "检索语言"),
    "details": ("See the backend records for evidence and follow-up tasks.", "详细依据和后续任务见后台记录。"),
    "counts": ("{total} documents, {complete} complete local files, {partial} partial files, {missing} without a local file.",
               "{total} 条资料，{complete} 份完整本地文件，{partial} 份部分正文，{missing} 条无本地文件。"),
    "invalid_file": ("File check failed ({reason}). Original retained for review.", "文件检查异常（{reason}）。原件留待核验。"),
    "duplicate": ("Matching file bytes. Check identity and versions.", "附件字节相同，请核对身份和版本。"),
    "review_file": ("Local copy retained pending verification of identity or body.", "本地文件已保留，身份或正文范围待核验。"),
}


def text(value, language, fallback=""):
    """Render a free-text locale mapping or retain the original string."""
    if isinstance(value, str):
        return value
    value = value or {}
    en, zh = value.get("en", ""), value.get("zh-CN", "")
    if language == "bilingual":
        return " / ".join(dict.fromkeys(x for x in (en, zh) if x)) or fallback
    return (en or zh if language == "en" else zh or en) or fallback


def label(key, language, separator=" / "):
    if key not in LABELS:
        return key
    en, zh = LABELS[key]
    if language == "bilingual":
        return en if en == zh else separator.join((en, zh))
    return en if language == "en" else zh


def folder(key, language):
    return label(key, language, " - ")


def folders(key):
    return {folder(key, language) for language in LANGUAGES}


def output_language(config, override=None):
    language = override or config.get("output_language")
    if not language:
        language = "zh-CN" if str(config.get("user_language", "")).lower().startswith("zh") else "en"
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported output language: {language}")
    return language
