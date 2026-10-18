#!/usr/bin/env python3
"""受控中文确定性 linter（stdlib only）。

只查「不靠理解语义就能指出具体那个词或那个标点」的规则。三条边界：

1. 永远不查情态。可能 / 也许 / 大概 / 估计 / 大概率 / 不排除 是作者给出的置信度，
   是内容，不是赘肉。一个会逼着人删掉这些词的 linter 会让文本变得比原文更假。
2. 不查零指代和意合。判断一个句子有没有主语、两个分句之间是因果还是并列，
   需要句法分析，正则做不到。这两条只写在 SKILL.md 里，交给人。
   （只兜一个高频子集：以「已 / 待 / 未 / 尚未」开头的无主状态句。）
3. 不判断改得对不对。零违规只说明这里配的规则没找到问题，不说明改写保住了原意。

用法:
    zh-lint.py FILE [FILE ...]
    echo "文本" | zh-lint.py [--json]
    zh-lint.py --baseline 5 FILE       # 硬违规超过 5 才失败（存量文档接入）
    zh-lint.py --disable vague-time,buzzword FILE
    zh-lint.py --selftest

退出码: 0 通过；1 硬违规超过 baseline（默认 0）；2 用法错误。
建议类（advisory）发现永不导致失败。
"""
import argparse
import bisect
import contextlib
import io
import json
import os
import re
import sys
import tempfile

# --------------------------------------------------------------------------
# 词表。与 references/lexicon.md 是同一份词表的两处表达，改一处要同步另一处。
# --------------------------------------------------------------------------

# 空时间词：读者读完仍不知道什么时候。注意这组不含「可能」「以后」——
# 那两样是情态和时间方向，是内容。
VAGUE_TIME = (
    "尽快|尽早|及时|第一时间|适时|随时|近期|近日|短期内|后续|稍后|争取"
)

# 条件词：条件是空的，动作就无从执行。
VAGUE_CONDITION = "必要时|视情况|酌情|原则上|按需|如有需要|根据需要|在适当的时候"

# 数量词：没有数字就没有验收标准。
VAGUE_QUANTITY = "适当|适度|适量|少量|若干|一大批|一定程度|一定范围|加大力度|多措并举"

# 范围词：谁来做没写，等于没安排。
VAGUE_SCOPE = (
    r"(?:相关|有关|相应|主管)(?:部门|人员|单位|内容|材料|文件|信息|要求|规定|事项)"
    r"|有关单位|相关部门"
)

# 虚动词：动作被冻成名词，前面垫一个不承载信息的动词。
EMPTY_VERB = (
    r"(?:进行|加以|予以|作出|给予|开展|实施)"
    r"(?:了|一次|进一步|全面|统一|认真)?"
    r"(?:优化|分析|评估|检查|处理|确认|整改|提升|改进|梳理|排查|备份|测试|审核|审批|"
    r"统计|汇总|核实|部署|配置|迁移|归档|回滚|拆分|研究|论证|修订|清理|修改|调整|"
    r"完善|落实|推动|规范|安排|汇报|讨论)"
)

# 行话：不指任何具体动作，只指「我们做了很专业的事」。
BUZZWORD = (
    "赋能|抓手|闭环|打通|链路|颗粒度|对齐|沉淀|组合拳|护城河|颠覆式|降维|心智|势能|"
    "飞轮|壁垒|拉齐|倒逼|下半场|第一性原理|顶层设计|生态位|认知升级|能力建设|价值闭环|"
    r"all[- ]?in"
)

# 套话：删掉之后句子不丢任何信息。
FILLER = (
    "需要注意的是|需要指出的是|值得一提|值得一提的是|众所周知|总的来说|综上所述|"
    "在一定程度上|从某种意义上|毋庸置疑|显而易见|不得不说|不难看出|也就是说"
)

# 双重否定：读者要算两次才能还原意思。
DOUBLE_NEGATIVE = "不无|未必不|不能不|无不|未尝不|不无道理"

# 义务/禁止用词的近义轮换。制度类文本默认统一用「应当」和「不得 / 禁止」。
# 「应」和「须」单独成词时要躲开 应用 / 须知 这类复音词。
OBLIGATION_PATTERNS = [
    ("应当", re.compile("应当")),
    ("必须", re.compile("必须")),
    ("务必", re.compile("务必")),
    ("须", re.compile("须(?![知要])")),
    ("应", re.compile("应(?![用该当急力付答届试聘收邀变有是按声])")),
]
BAN_WORDS = "严禁|不准|不应|不宜"

# 一词一义：同一动作/对象只留一个名字。只收真正可以互换的组，
# 近义但不同义的（错误 / 故障 / 失败）不进组。
SYNONYM_GROUPS = [
    ("删除", "移除", "清除"),
    ("用户", "客户", "使用者", "会员"),
    ("修改", "更改", "变更"),
    ("开始", "启动", "开启"),
    ("显示", "展示", "呈现"),
    ("获取", "拉取", "读取"),
    ("发送", "推送", "投递"),
]

RULES = [
    ("semicolon", "advisory-free",
     re.compile(r"；|;"),
     "分号把两个动作焊在一句里。拆成两句，或改成列表。"),
    ("halfwidth-punct", "advisory-free",
     re.compile(r"(?<=[\u4e00-\u9fff])[,;:?!]|[,;:?!](?=[\u4e00-\u9fff])|(?<=[\u4e00-\u9fff])\.(?![0-9])"),
     "中文里用了半角标点。改成全角（，：？！；。），代码和英文串除外。"),
    ("vague-time", "advisory-free",
     re.compile(VAGUE_TIME),
     "空时间词：读者读完仍不知道什么时候。写出时长、截止时间，或明说「时间未定，待 X 确认」。"),
    ("vague-condition", "advisory-free",
     re.compile(VAGUE_CONDITION),
     "空条件词：条件没写清，动作就无从执行。写出触发条件，或写明「本条不设条件」。"),
    ("vague-quantity", "advisory-free",
     re.compile(VAGUE_QUANTITY),
     "空数量词：没有数字就没有验收标准。写出数量、单位、阈值。"),
    ("vague-scope", "advisory-free",
     re.compile(VAGUE_SCOPE),
     "范围没有落到具体主体上。写出主体名称、岗位或角色。"),
    ("empty-verb", "advisory-free",
     re.compile(EMPTY_VERB),
     "虚动词：动作被冻成了名词。直接用后面的动词（「进行分析」→「分析」）。"),
    ("buzzword", "advisory-free",
     re.compile(BUZZWORD),
     "行话：它不指任何具体动作，只暗示事情很专业。换成具体做了什么。"),
    ("filler", "advisory-free",
     re.compile(FILLER),
     "套话：删掉之后句子不丢信息。直接说事。"),
    ("double-negative", "advisory-free",
     re.compile(DOUBLE_NEGATIVE),
     "双重否定：读者要算两次才知道你是肯定还是否定。改成直说。"),
    ("ban-verb", "advisory",
     re.compile(BAN_WORDS),
     "禁止性用词不统一。有主语用「不得」，无主语祈使句用「禁止」，全篇只留这两类。"),
    ("range-unmarked", "advisory-free",
     re.compile(r"[0-9零一二两三四五六七八九十百千万几]+\s*(?:个|名|人|天|日|小时|分钟|"
                r"工作日|月|年|周|次|项|元|万|台|件|份|行)?\s*(?:以上|以下|以内)"),
     "范围边界没说含不含本数。写成「≥ 3 个工作日」或「3 个工作日以上（含）」。"),
    ("halfwidth-paren", "advisory",
     re.compile(r"[\u4e00-\u9fff]\([^)]*\)"),
     "中文句子里的括号用了半角。改成全角（），例外是代码和英文单位。"),
    ("de-chain", "advisory",
     re.compile(r"(?:[^。！？]{0,40}的[^。！？]{0,40}){3,}"),
     "「的」链太长：定语一层套一层，读者要倒着拆。拆成两句，或把定语改成动作。"),
    ("anonymous-status", "advisory",
     re.compile(r"(?:^|(?<=[，。；！？\n]))(?:已|待|未|尚未|正在)(?:经)?"
                r"[\u4e00-\u9fa5]{1,4}了?(?=[，。；！？\n]|$)"),
     "以「已/待/未」开头的状态句省掉了施事。读者不知道谁做的、该找谁确认。补主语。"),
    ("actorless-passive", "advisory",
     re.compile(r"被[\u4e00-\u9fa5]{1,3}(?:了)?(?=[，。；！？]|$)"),
     "「被」字句没有施事。写出谁做的；施事确实无关时才保留被动。"),
]

MAX_CHARS_INSTRUCTION = 25   # 指令句上限
MAX_CHARS_DESCRIPTION = 40   # 说明句上限

# 情态词：永不拦截。selftest 里有断言守着这一条。
MODALITY = ("可能", "也许", "大概", "估计", "大概率", "或许", "不排除", "倾向于", "据")

INSTRUCTION_LEAD = re.compile(
    r"^(?:请|务必|须|必须|应当|应|需|不要|不得|禁止|严禁|"
    r"点击|打开|输入|选择|确认|填写|提交|删除|保存|关闭|上传|下载|登录|退出|忽略)"
)

LOGIC_WORDS = ("如果", "若", "当", "因为", "由于", "所以", "因此", "除非", "否则",
               "只有", "只要", "即使", "虽然", "但是", "但", "以为", "以致", "为了")

CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN_TOKEN = re.compile(r"[A-Za-z0-9_]+")
CODE_FENCE = re.compile(r"^(?:```|~~~)")
INLINE_CODE = re.compile(r"`[^`]*`")
LIST_ITEM_START = re.compile(
    r"^(?P<indent> {0,3})(?P<marker>[-*+]|[0-9]+[.)、]|[（(][0-9一二三四五六七八九十]+[）)])(?P<gap> +)(?P<body>.*)$"
)
STANDALONE_LINE = re.compile(r"^ {0,3}(?:#|<|(?:[-*_=] *){3,}$)")
# 「未定 / 保留原样」是改写记录，不是正文。它们按设计会引用原文里的违规词，
# 所以整行不扫——否则每份合规的改写都会被自己的备注判违规。
META_LINE = re.compile(r"^\s*(?:>\s*)*(?:未定|保留原样)\s*[:：]")
BLOCKQUOTE_PREFIX = re.compile(r"^ {0,3}(?:> ?)+")
ANY_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|[0-9]+[.)、]|[（(][0-9一二三四五六七八九十]+[）)])(?:\s|$)")
TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
SENTENCE_END = re.compile(r"[。！？]+[”’」』）)\]】》]*")
DANGLING_END = re.compile(r"(?:[、和或与及]|以及|并且|同时|或者)$")


def char_count(text):
    """字数 = 汉字个数 + 连续的拉丁字母/数字串个数。标点不计。"""
    return len(CJK.findall(text)) + len(LATIN_TOKEN.findall(text))


def _mask_inline_code(text):
    """把行内代码抹成等长空格，让列号仍然对得上源文件。"""
    return INLINE_CODE.sub(lambda m: " " * len(m.group(0)), text)


def _split_table_row(line):
    left = len(line) - len(line.lstrip())
    right = len(line.rstrip())
    content = line[left:right]
    if "|" not in content:
        return None
    if content.startswith("|"):
        content = content[1:]
        left += 1
    if content.endswith("|"):
        content = content[:-1]
    raw_cells = re.split(r"(?<!\\)\|", content)
    if len(raw_cells) < 2:
        return None
    cells, column = [], left
    for raw in raw_cells:
        lead = len(raw) - len(raw.lstrip())
        cells.append((raw.strip(), column + lead))
        column += len(raw) + 1
    return cells


def _markdown_table_cells(lines):
    """普通 Markdown 表格 -> 每个单元格单独成一个 prose block。"""
    table_cells, index = {}, 1
    while index < len(lines):
        sep = _split_table_row(lines[index])
        head = _split_table_row(lines[index - 1])
        if (not sep or not head or len(sep) != len(head)
                or not all(TABLE_SEPARATOR_CELL.fullmatch(cell) for cell, _ in sep)):
            index += 1
            continue
        table_cells[index - 1] = head
        table_cells[index] = []
        index += 1
        while index < len(lines):
            row = _split_table_row(lines[index])
            if not row or len(row) != len(sep):
                break
            table_cells[index] = row
            index += 1
    return table_cells


def _split_sentences(text):
    """返回 [(起始偏移, 句子)]。中文句末在 。！？，后接引号/括号也计入。"""
    out, pos = [], 0
    for m in SENTENCE_END.finditer(text):
        seg = text[pos:m.end()]
        if seg.strip():
            out.append((pos, seg))
        pos = m.end()
    if text[pos:].strip():
        out.append((pos, text[pos:]))
    return out


def _long_sentence_findings(pieces, filename):
    """pieces: [(lineno, source_column, text)]，拼起来按句查超长。"""
    offsets, position = [], 0
    for _, _, text in pieces:
        offsets.append(position)
        position += len(text)
    joined = "".join(text for _, _, text in pieces)
    findings = []
    for start, sentence in _split_sentences(joined):
        n = char_count(sentence)
        cap = MAX_CHARS_INSTRUCTION if INSTRUCTION_LEAD.match(sentence.strip()) \
            else MAX_CHARS_DESCRIPTION
        if n <= cap:
            continue
        index = bisect.bisect_right(offsets, start) - 1
        lineno, source_column, _ = pieces[index]
        findings.append({
            "file": filename, "line": lineno,
            "col": source_column + start - offsets[index] + 1,
            "rule": "long-sentence", "level": "advisory-free",
            "match": f"{n} 字",
            "message": f"句子 {n} 字（上限 {cap}）。一个动作一句，或拆成列表。",
        })
    return findings


def _parataxis_findings(pieces, filename):
    """逗号串了三个以上分句、又没有任何逻辑词 —— 逻辑关系靠读者补。"""
    offsets, position = [], 0
    for _, _, text in pieces:
        offsets.append(position)
        position += len(text)
    joined = "".join(text for _, _, text in pieces)
    findings = []
    for start, sentence in _split_sentences(joined):
        if sentence.count("，") < 3:
            continue
        if any(word in sentence for word in LOGIC_WORDS):
            continue
        index = bisect.bisect_right(offsets, start) - 1
        lineno, source_column, _ = pieces[index]
        findings.append({
            "file": filename, "line": lineno,
            "col": source_column + start - offsets[index] + 1,
            "rule": "parataxis", "level": "advisory",
            "match": f"{sentence.count('，') + 1} 个分句",
            "message": "逗号串起了多个分句，逻辑关系要读者自己补。用「如果…就…」「因为…所以…」写出来，或拆句。",
        })
    return findings


def _leading_spaces(line):
    return len(line) - len(line.lstrip(" "))


def _is_list_continuation(line, content_indent):
    if not line.strip():
        return True
    if LIST_ITEM_START.match(line):
        return False
    return _leading_spaces(line) >= content_indent


def _dangling_conjunction_findings(text, filename):
    """列表项最后一行以「、/和/或/以及/并且/同时」结尾：句子没说完。"""
    lines = text.splitlines()
    findings, in_fence, index = [], False, 0
    while index < len(lines):
        line = lines[index]
        if CODE_FENCE.match(line.strip()):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence:
            index += 1
            continue
        start = LIST_ITEM_START.match(line)
        if not start:
            index += 1
            continue
        content_indent = (len(start.group("indent")) + len(start.group("marker"))
                          + len(start.group("gap")))
        item_lines = [(index, start.group("body"))]
        next_index = index + 1
        item_fence = False
        while next_index < len(lines):
            candidate = lines[next_index]
            if CODE_FENCE.match(candidate.strip()):
                item_fence = not item_fence
                next_index += 1
                continue
            if item_fence or not _is_list_continuation(candidate, content_indent):
                break
            item_lines.append((next_index, candidate))
            next_index += 1
        meaningful = []
        for line_index, item_line in item_lines:
            cleaned = INLINE_CODE.sub(" 代码 ", item_line).strip()
            cleaned = cleaned.strip("*_` ")
            if cleaned:
                meaningful.append((line_index, cleaned))
        if meaningful:
            end_index, end_line = meaningful[-1]
            if DANGLING_END.search(end_line) and not end_line.endswith("：") and not end_line.endswith(":"):
                raw = next(raw for line_index, raw in item_lines if line_index == end_index)
                masked = INLINE_CODE.sub(lambda m: " " * len(m.group(0)), raw)
                pos = len(masked.rstrip()) - 1
                findings.append({
                    "file": filename,
                    "line": end_index + 1 if end_index != index else index + 1,
                    "col": pos + 1,
                    "rule": "dangling-conjunction", "level": "advisory-free",
                    "match": end_line,
                    "message": "列表项以「、/和/或/以及/并且」结尾，话没说完。补全，或把下一项并进来。",
                })
        index = next_index
    return findings


def _obligation_findings(text, filename):
    """义务词轮换：同一篇里出现两种以上（应当 / 必须 / 务必 / 须 / 应）。"""
    seen = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        if META_LINE.match(line):
            continue
        masked = _mask_inline_code(line)
        for word, pattern in OBLIGATION_PATTERNS:
            if word in seen:
                continue
            m = pattern.search(masked)
            if m:
                seen[word] = (lineno, m.start() + 1)
    # 「应当」里的「应」、「必须」里的「须」不算第二种用法。
    if "应当" in seen:
        seen.pop("应", None)
    if "必须" in seen:
        seen.pop("须", None)
    if len(seen) < 2:
        return []
    keep = next(word for word, _ in OBLIGATION_PATTERNS if word in seen)
    findings = []
    for word, (lineno, col) in seen.items():
        if word == keep:
            continue
        findings.append({
            "file": filename, "line": lineno, "col": col,
            "rule": "obligation-mix", "level": "advisory-free",
            "match": word,
            "message": f"义务词轮换：用了「{word}」，前面用的是「{keep}」。全篇只留一个（制度类默认「应当」）。",
        })
    return findings


def _date_unit_findings(text, filename):
    """时限单位混用：一边说「3 日」，一边说「3 个工作日」。"""
    patterns = {
        "日": re.compile(r"[0-9一二三四五六七八九十]+\s*(?:个)?日(?![本常历程期])"),
        "工作日": re.compile(r"[0-9一二三四五六七八九十]+\s*个?\s*工作日"),
    }
    seen = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        if META_LINE.match(line):
            continue
        masked = _mask_inline_code(line)
        for unit, pattern in patterns.items():
            m = pattern.search(masked)
            if m and unit not in seen:
                seen[unit] = (lineno, m.start() + 1)
    if len(seen) < 2:
        return []
    unit_keep = next(iter(seen))
    other = next(u for u in seen if u != unit_keep)
    lineno, col = seen[other]
    return [{
        "file": filename, "line": lineno, "col": col,
        "rule": "date-unit-mix", "level": "advisory-free",
        "match": other,
        "message": f"时限单位混用：「{unit_keep}」和「{other}」在法定期限里不是一回事。全篇锁定一种，并写出起算点。",
    }]


def lint(text, filename="<stdin>"):
    findings = []
    lines = text.splitlines()
    table_cells = _markdown_table_cells(lines)
    seen_synonyms = {}
    in_fence = False
    in_quote = False
    block = []
    total_chars = 0

    def flush():
        if block:
            findings.extend(_long_sentence_findings(block, filename))
            findings.extend(_parataxis_findings(block, filename))
            block.clear()

    for lineno, raw_line in enumerate(lines, 1):
        if CODE_FENCE.match(raw_line.strip()):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if META_LINE.match(raw_line):
            flush()
            continue
        segments = table_cells.get(lineno - 1, [(raw_line, 0)])
        is_table = (lineno - 1) in table_cells
        quote = BLOCKQUOTE_PREFIX.match(raw_line)
        is_quote = bool(quote)
        content = raw_line[quote.end():] if quote else raw_line
        standalone = STANDALONE_LINE.match(content)
        if (is_table or not content.strip() or standalone
                or ANY_LIST_ITEM.match(content) or is_quote != in_quote):
            flush()
        in_quote = is_quote

        for segment, source_column in segments:
            masked = _mask_inline_code(segment)
            total_chars += char_count(masked)
            for rule_id, level, pattern, msg in RULES:
                for m in pattern.finditer(masked):
                    findings.append({
                        "file": filename, "line": lineno,
                        "col": source_column + m.start() + 1,
                        "rule": rule_id, "level": level,
                        "match": m.group(0), "message": msg,
                    })
            for gi, group in enumerate(SYNONYM_GROUPS):
                for base in group:
                    if (gi, base) in seen_synonyms:
                        continue
                    pos = masked.find(base)
                    if pos >= 0:
                        seen_synonyms[(gi, base)] = (lineno, source_column + pos + 1, base)
            if is_table:
                flush()
        if standalone:
            flush()
        if not is_table and not standalone and not ANY_LIST_ITEM.match(content) and content.strip():
            skip = quote.end() if quote else 0
            block.append((lineno, skip + 1, masked[skip:]))
    flush()

    for gi, group in enumerate(SYNONYM_GROUPS):
        present = sorted((seen_synonyms[(gi, b)], b) for b in group if (gi, b) in seen_synonyms)
        if len(present) > 1:
            first = present[0][1]
            for (lineno, col, _), base in present[1:]:
                findings.append({
                    "file": filename, "line": lineno, "col": col,
                    "rule": "synonym-rotation", "level": "advisory-free",
                    "match": base,
                    "message": f"「{base}」和「{first}」指同一件事。挑一个，全篇用它。",
                })

    findings.extend(_dangling_conjunction_findings(text, filename))
    findings.extend(_obligation_findings(text, filename))
    findings.extend(_date_unit_findings(text, filename))
    findings.sort(key=lambda f: (f["line"], f["col"], f["rule"]))
    return findings, total_chars


RULE_IDS = ({rule_id for rule_id, *_ in RULES}
            | {"long-sentence", "parataxis", "dangling-conjunction",
               "synonym-rotation", "obligation-mix", "date-unit-mix"})


def report(findings, total_chars, as_json, hard_count, baseline):
    rate = round(len(findings) * 100 / total_chars, 1) if total_chars else 0.0
    if as_json:
        print(json.dumps({"violations": findings, "count": len(findings),
                          "hard_count": hard_count, "baseline": baseline,
                          "chars": total_chars, "per_100_chars": rate},
                         ensure_ascii=False, indent=2))
        return
    for f in findings:
        print(f"{f['file']}:{f['line']}:{f['col']} {f['rule']}: {f['message']} [{f['match']}]")
    print(f"\n{len(findings)} 处（硬违规 {hard_count}，baseline {baseline}），"
          f"{total_chars} 字，每 100 字 {rate} 处")
    print("情态（可能 / 也许 / 大概 / 不排除）永不标注：置信度是内容。")


def selftest():
    # 每条硬规则都能抓到自己的样本
    bad = "尽快处理；需要注意的是这件事不无道理，进行优化，赋能业务，3 天以上完成。"
    findings, _ = lint(bad)
    rules = {f["rule"] for f in findings}
    for expected in ("semicolon", "vague-time", "filler", "double-negative",
                     "empty-verb", "buzzword", "range-unmarked"):
        assert expected in rules, (expected, rules)

    # 情态永不拦截，包括最容易被句长规则顺手删掉的那几个
    quiet = ("请求可能已经失败。日志也许是超时导致的。我估计要 3 次。"
             "大概率是客户端版本。不排除缓存过期。")
    findings, _ = lint(quiet)
    assert findings == [], findings
    for word in MODALITY:
        findings, _ = lint(f"情况{word}变化。")
        assert not any(f["rule"] in {"vague-time", "vague-condition"} for f in findings), (word, findings)

    # 代码块、行内代码、表格分隔行都不算正文
    findings, _ = lint("```\nx = a; y = b\n尽快\n```")
    assert findings == [], findings
    findings, _ = lint("调用 `fast_尽快()` 即可。")
    assert not any(f["rule"] == "vague-time" for f in findings), findings
    findings, _ = lint("| 项 | 值 |\n| --- | --- |\n| a | b |")
    assert findings == [], findings

    # 硬违规 > baseline 才失败；建议类不失败
    findings, chars = lint("文件被删除了。")
    hard = sum(1 for f in findings if f["level"] == "advisory-free")
    assert hard == 0 and any(f["rule"] == "actorless-passive" for f in findings), findings
    assert chars == 6, chars

    # 超长句：指令句 25 字、说明句 40 字，按汉字计不按空格计
    twenty_six = "请" + "填" * 25 + "。"
    findings, _ = lint(twenty_six)
    assert any(f["rule"] == "long-sentence" for f in findings), findings
    findings, _ = lint("请" + "填" * 24 + "。")
    assert not any(f["rule"] == "long-sentence" for f in findings), findings
    findings, _ = lint("说" + "明" * 39 + "。")
    assert not any(f["rule"] == "long-sentence" for f in findings), findings
    findings, _ = lint("说" + "明" * 41 + "。")
    assert any(f["rule"] == "long-sentence" for f in findings), findings

    # 意合：三个以上逗号分句、又没有逻辑词才报
    findings, _ = lint("打开文件，读取第三行，比对签名，写回结果。")
    assert any(f["rule"] == "parataxis" for f in findings), findings
    findings, _ = lint("如果签名不匹配，就跳过，记录日志，然后继续。")
    assert not any(f["rule"] == "parataxis" for f in findings), findings

    # 无主状态句抓高频子集，有主语的句子不抓
    findings, _ = lint("已完成，请查收。")
    assert any(f["rule"] == "anonymous-status" for f in findings), findings
    findings, _ = lint("报表已完成了。")
    assert not any(f["rule"] == "anonymous-status" for f in findings), findings

    # 一词一义：第二个名字被点名，并指出保留的是哪个
    findings, _ = lint("删除这条记录，然后移除缓存。")
    rot = [f for f in findings if f["rule"] == "synonym-rotation"]
    assert len(rot) == 1 and "移除" in rot[0]["message"] and "删除" in rot[0]["message"], rot
    findings, _ = lint("删除这条记录，再删除缓存。")
    assert not any(f["rule"] == "synonym-rotation" for f in findings), findings

    # 义务词与禁止性用词
    findings, _ = lint("操作前必须备份。提交后应当复核。")
    assert any(f["rule"] == "obligation-mix" for f in findings), findings
    findings, _ = lint("操作前应当备份。提交后应当复核。")
    assert not any(f["rule"] == "obligation-mix" for f in findings), findings
    findings, _ = lint("严禁遮挡消防通道。")
    assert any(f["rule"] == "ban-verb" for f in findings), findings

    # 「未定 / 保留原样」是记录行，按设计会引用原文的违规词，整行不扫
    findings, _ = lint("请重试。\n未定：重试间隔（原文「稍后」）\n保留原样：保留了「不排除」")
    assert findings == [], findings

    # 时限单位混用
    findings, _ = lint("3 日内提交，另附 5 个工作日内的说明。")
    assert any(f["rule"] == "date-unit-mix" for f in findings), findings
    findings, _ = lint("3 个工作日内提交。")
    assert not any(f["rule"] == "date-unit-mix" for f in findings), findings

    # 范围词：标了含不含本数就不报
    findings, _ = lint("3 个工作日以上（含）提交。")
    assert not any(f["rule"] == "range-unmarked" for f in findings), findings

    # 列表项没说完
    findings, _ = lint("- 提交申请表和\n- 等待审核")
    dangling = [f for f in findings if f["rule"] == "dangling-conjunction"]
    assert len(dangling) == 1 and dangling[0]["line"] == 1, dangling
    findings, _ = lint("- 提交申请表以及\n  身份证明")
    assert not any(f["rule"] == "dangling-conjunction" for f in findings), findings
    findings, _ = lint("```\n- 甲和\n```")
    assert not any(f["rule"] == "dangling-conjunction" for f in findings)

    # 半角标点，列号对得上源文件
    findings, _ = lint("注意: 这里要用全角。")
    punct = [f for f in findings if f["rule"] == "halfwidth-punct"]
    assert len(punct) == 1 and punct[0]["col"] == 3, punct

    # 命令行：交错参数、json、用法错误
    with tempfile.TemporaryDirectory() as tmp:
        paths = [os.path.join(tmp, name) for name in ("a.md", "b.md")]
        for path in paths:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("尽快提交。\n")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert main([paths[0], "--json", paths[1]]) == 1
        assert json.loads(out.getvalue())["chars"] == 8, out.getvalue()
    for argv in (["--basline", "3"], ["--baseline"], ["--baseline", "x"],
                 ["--baseline", "-1"], ["--disable", "nope"], ["--base", "3"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                main(argv)
        except SystemExit as e:
            assert e.code == 2, (argv, e.code)
        else:
            raise AssertionError(argv)
    # baseline 容忍存量文档
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as fh:
        fh.write("尽快；处理。\n")
        path = fh.name
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            assert main([path, "--baseline", "2"]) == 0
            assert main(["--disable", "semicolon,vague-time", path]) == 0
    finally:
        os.unlink(path)
    print("selftest OK")


def _rule_list(value):
    rules = {r for r in value.split(",") if r}
    unknown = rules - RULE_IDS
    if unknown:
        raise argparse.ArgumentTypeError(
            f"未知规则：{', '.join(sorted(unknown))}。已知规则：{', '.join(sorted(RULE_IDS))}")
    return rules


def _non_negative_int(value):
    try:
        n = int(value)
    except ValueError:
        n = -1
    if n < 0:
        raise argparse.ArgumentTypeError(f"需要非负整数，收到 {value!r}")
    return n


def main(argv):
    parser = argparse.ArgumentParser(
        prog="zh-lint.py", allow_abbrev=False,
        description="受控中文确定性 linter。不给 FILE 时读 stdin。")
    parser.add_argument("paths", nargs="*", metavar="FILE")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--baseline", type=_non_negative_int, default=0, metavar="N",
                        help="硬违规不超过 N 就算通过（默认 0）")
    parser.add_argument("--disable", type=_rule_list, default=set(), metavar="RULES",
                        help="逗号分隔的规则名，关掉它们")
    parser.add_argument("--selftest", action="store_true", help="跑内置测试")
    args = parser.parse_intermixed_args(argv)
    if args.selftest:
        selftest()
        return 0

    findings, total_chars = [], 0
    if args.paths:
        for path in args.paths:
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except OSError as e:
                parser.error(f"读不了 {path}：{e.strerror}")
            got, chars = lint(text, filename=path)
            findings.extend(got)
            total_chars += chars
    else:
        findings, total_chars = lint(sys.stdin.read())

    findings = [f for f in findings if f["rule"] not in args.disable]
    hard_count = sum(1 for f in findings if f["level"] == "advisory-free")
    report(findings, total_chars, args.json, hard_count, args.baseline)
    return 1 if hard_count > args.baseline else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
