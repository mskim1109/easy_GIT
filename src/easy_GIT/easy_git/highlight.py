"""코드 줄을 VS Code 기본 다크(Dark+) 색으로 나눈다. Pygments 는 rich 와 함께 이미 설치되어 있다."""

from functools import lru_cache
from pathlib import PurePath

from pygments.lexer import Lexer
from pygments.lexers import get_lexer_for_filename
from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, String, Token, _TokenType
from pygments.util import ClassNotFound

# VS Code Dark+ 색
DEFAULT = "#D4D4D4"
KEYWORD = "#569CD6"   # def, class, const, True, None
CONTROL = "#C586C0"   # if, for, return, import
FUNCTION = "#DCDCAA"
CLASS = "#4EC9B0"
VARIABLE = "#9CDCFE"
STRING = "#CE9178"
NUMBER = "#B5CEA8"
COMMENT = "#6A9955"
ESCAPE = "#D7BA7D"
REGEX = "#D16969"

COLORS = {  # 없으면 가장 가까운 부모 토큰의 색
    Comment: COMMENT,
    String: STRING, String.Escape: ESCAPE, String.Regex: REGEX,
    Number: NUMBER,
    Keyword: KEYWORD, Keyword.Namespace: CONTROL, Operator.Word: KEYWORD,
    Name: VARIABLE, Name.Attribute: VARIABLE,
    Name.Function: FUNCTION, Name.Builtin: FUNCTION, Name.Decorator: FUNCTION,
    Name.Builtin.Pseudo: KEYWORD, Name.Tag: KEYWORD,
    Name.Class: CLASS, Name.Namespace: CLASS,
}
CONTROL_WORDS = {
    "if", "elif", "else", "for", "while", "do", "return", "break", "continue", "try", "except", "catch",
    "finally", "raise", "throw", "with", "yield", "await", "import", "from", "as", "pass", "switch", "case",
    "default", "goto", "export", "match",
}

Line = list[tuple[str, str]]  # (글, 색) 조각들


@lru_cache(maxsize=64)
def _lexer(suffix: str) -> Lexer | None:
    try:  # stripnl=False: 앞뒤 빈 줄을 지우면 줄 번호가 어긋난다
        return get_lexer_for_filename("x" + suffix, stripnl=False)
    except ClassNotFound:
        return None


def _color(ttype: _TokenType, value: str) -> str:
    if ttype in Keyword and value in CONTROL_WORDS:
        return CONTROL
    while ttype not in COLORS and ttype.parent is not None:
        ttype = ttype.parent
    return COLORS.get(ttype, DEFAULT)


def highlight_lines(lines: list[str], path: str) -> list[Line]:
    """파일 전체를 한 번에 분석해(여러 줄 문자열·주석 때문에) 줄마다 (글, 색) 조각으로 돌려준다."""
    lexer = _lexer(PurePath(path).suffix.lower()) if PurePath(path).suffix else None
    if lexer is None:
        return [[(line, DEFAULT)] if line else [] for line in lines]
    tokens = list(lexer.get_tokens("\n".join(lines) + "\n"))
    out: list[Line] = [[]]
    for i, (ttype, value) in enumerate(tokens):
        color = _color(ttype, value)
        if ttype is Token.Name:  # 공백 다음에 ( 가 오면 호출: VS Code 처럼 함수 색
            k = i + 1
            while k < len(tokens) and not tokens[k][1].strip():
                k += 1
            if k < len(tokens) and tokens[k][0] in Punctuation and tokens[k][1].startswith("("):
                color = FUNCTION
        for j, part in enumerate(value.split("\n")):
            if j:
                out.append([])
            if part:
                out[-1].append((part, color))
    return out[: len(lines)]
