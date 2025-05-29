import os
import re
import subprocess
import sys

SCRIPT_DIR_PYTHON = os.path.dirname(os.path.abspath(__file__))

LUA_TABLE_FLATTENER_FILTER = os.path.join(
    SCRIPT_DIR_PYTHON, "table_flattener.lua"
)


def remove_unwanted_spans(text: str) -> str:
    """
    특정 패턴의 불필요한 <span> 태그를 내용물만 남기고 제거합니다.
    예: <span id="..." startref="..." data-type="indexterm">내용물</span> -> 내용물
    """
    # <span id="ch<숫자>.html" ...> (선택적 공백) </span> 패턴을 찾아 완전히 제거
    text = re.sub(
        r'<span\s+id="ch[0-9]+\.html"[^>]*>\s*<\/span>',
        "",
        text,
        flags=re.IGNORECASE,
    )
    # data-type="indexterm"을 가진 span 제거 (내용물 유지)
    text = re.sub(
        r"<span\s+[^>]*?data-type=\"indexterm\"[^>]*>(.*?)<\/span>",
        r"\1",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # 다른 불필요한 span 패턴도 여기에 추가 가능
    # 예: ID만 있는 span 제거 (내용물 유지) - 매우 광범위하므로 주의
    # text = re.sub(r"<span\s+id=\"(?:[^\"]*)\"[^>]*>(.*?)<\/span>", r"\1", text, flags=re.IGNORECASE | re.DOTALL)
    return text


def convert_smart_quotes(text):
    """스마트 따옴표를 직선 따옴표로 변환합니다."""
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    return text


def fix_footnote_definitions(text):
    """
    각주 정의 형식을 수정합니다.
    예: ^([1](#anchor)) Caption text -> [^1]: Caption text
    """
    # 주의: 이 정규식은 라인 시작 부분의 패턴만 정확히 일치시킵니다.
    # 만약 각주 정의가 여러 줄에 걸쳐 있거나 더 복잡한 구조라면 수정이 필요할 수 있습니다.
    return re.sub(
        r"^\^\(\[([0-9]+)\]\(#[^)]+\)\)\s*(.*)",
        r"[^\1]: \2",
        text,
        flags=re.MULTILINE,
    )


def convert_image_captions_to_figures(text, media_folder_name):
    """
    마크다운 이미지 + H6 캡션 패턴을 HTML <figure> 태그로 변환합니다.
    이미지: ![alt text](./media_folder/image.png)
    캡션: ###### Figure 1-3. Caption text with [link](url)
    """

    # media_folder_name 내부의 특수문자 이스케이프 (정규식 패턴에 사용하기 위함)
    escaped_media_folder = re.escape(media_folder_name)

    # 정규식 패턴:
    # 1. 이미지 라인: !\[(?P<alt>[^\]]*)\]\(.(?P<sep>/\Qmedia_folder_name\E/)(?P<filename>[^)]+)\)\s*\n
    #    (?P<alt>...): alt 텍스트 캡처
    #    (?P<sep>...): 경로 구분자 (./assets/ 또는 /assets/ 등) - 여기서는 MEDIA_FOLDER_NAME을 사용
    #    (?P<filename>...): 파일명 캡처
    #    (?P<src>...): 전체 이미지 경로 (아래 코드에서 재조합)
    # 2. (?:^\s*\n)*: 이미지와 캡션 사이의 선택적인 빈 줄들
    # 3. 캡션 라인: ^######\s*(?P<caption>.*?)\s*$ (비탐욕적 매칭)

    figure_pattern = re.compile(
        r"^!\[(?P<alt>[^\]]*)\]"  # Alt text
        r"\(.(?P<slash>/)"
        + escaped_media_folder
        + r"/(?P<filename>[^)]+)\)"  # Image src (./assets/file.png)
        r"\s*\n"  # End of image line
        r"(?:^\s*\n)*"  # Optional blank lines
        r"^######\s*(?P<caption>.*?)\s*$",  # H6 caption content (Markdown), non-greedy
        re.MULTILINE,
    )

    def replace_with_figure(match):
        alt_text = match.group("alt")
        slash = match.group("slash")  # 경로 시작이 ./ 또는 / 일 수 있음
        filename = match.group("filename")
        caption_md = match.group("caption")

        img_src = f".{slash}{media_folder_name}/{filename}"  # 경로 재구성

        # 캡션 마크다운을 HTML로 변환 (간단한 링크 변환 예시)
        # 더 복잡한 마크다운(볼드, 이탤릭 등) 변환이 필요하면 이 부분을 확장해야 합니다.
        caption_html = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', caption_md
        )

        # HTML 속성 값으로 사용될 수 있도록 alt 텍스트 이스케이프
        alt_text_html = alt_text.replace('"', "&quot;")

        return (
            f"<figure>\n"
            f'  <img src="{img_src}" alt="{alt_text_html}" />\n'
            f"  <figcaption>{caption_html}</figcaption>\n"
            f"</figure>\n"
        )

    return figure_pattern.sub(replace_with_figure, text)


def convert_h6_to_blockquote(text: str) -> str:
    """###### Tip, ###### Note, ###### Warning을 blockquote로 변환합니다.
    - ###### Tip -> [!Tip]
    - ###### Note -> [!Note]
    - ###### Caution -> [!Caution]
    - ###### Warning -> [!Warning]
    """
    return re.sub(
        r"^######\s*(Tip|Note|Caution|Warning)$",
        r"[!\1]",
        text,
        flags=re.MULTILINE,
    )


def adjust_headers(text: str) -> str:
    """
    마크다운 헤더 레벨을 조정하고 특정 예외 규칙을 적용합니다.
    """
    lines = text.splitlines()
    new_lines = []
    for line in lines:
        # 규칙 적용 순서가 중요합니다. 구체적인 예외부터 처리합니다.

        # 예외 3: ##### Example {숫자1}-{숫자2}. 내용 -> **Example {숫자1}-{숫자2}. 내용**
        # 예: "##### Example 1-2. Some title" -> "**Example 1-2. Some title**"
        match_ex3 = re.match(
            r"^(#####\s*)(Example\s+[0-9]+(?:-[0-9]+)?\..*)$", line
        )
        if match_ex3:
            # group(2)가 "Example X-Y. 내용" 부분입니다.
            new_lines.append(f"*{match_ex3.group(2).strip()}*")
            continue

        # 예외 2: # Chapter Goals -> ### Chapter Goals
        # 양 옆 공백을 제거하고 정확히 일치하는지 확인
        stripped_line = line.strip()
        if stripped_line == "# Chapter Goals":
            new_lines.append("### Chapter Goals")
            continue

        # 예외 1: # Chapter {숫자}는 그대로 둠
        # 예: "# Chapter 1", "# Chapter 12"
        # 라인 시작이 #, 공백, Chapter, 공백, 숫자(들), 그 뒤는 공백만 있거나 없음
        if re.match(r"^#\s+Chapter\s+[0-9.]+.*$", stripped_line):
            new_lines.append(line)  # 원본 라인 유지
            continue

        # 일반 규칙: H1~H5 헤더 레벨을 하나씩 늘림 (H6은 변경 안 함)
        #   # H1 -> ## H1
        #   ## H2 -> ### H2
        #   ...
        #   ##### H5 -> ###### H5
        #   ###### H6 -> ###### H6 (변경 없음)
        match_general = re.match(
            r"^(#{1,5})(\s+.*)$", line
        )  # H1부터 H5까지만 매칭
        if match_general:
            current_hashes = match_general.group(1)
            header_text_part = match_general.group(2)
            new_lines.append(f"#{current_hashes}{header_text_part}")
            continue

        # 위 모든 규칙에 해당하지 않는 라인은 그대로 추가
        new_lines.append(line)

    return "\n".join(new_lines)


def convert_superscript_footnotes(text: str) -> str:
    """
    <sup>{숫자}</sup> 형태의 각주 참조를 [^{숫자}]로 변환합니다.
    """
    pattern = r"^<sup>\[([0-9]+)\]\(#[^)]+\)<\/sup>\s+(.*)"
    replacement = r"[^\1]: \2"

    modified_text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    return modified_text


def process_html_figures(text: str) -> str:
    """
    HTML <figure> 블록을 처리합니다:
    1. <figure ...> 태그를 단순히 <figure>로 정규화합니다 (모든 속성 제거).
    2. 내부의 <h6...> 태그를 <figcaption...>으로 변경합니다 (<h6>의 속성은 유지).
    """

    # <figure>...</figure> 블록을 찾는 정규식
    # 그룹 1: <figure 태그와 그 안의 모든 내용 (여는 <figure ...> 태그부터 닫는 </figure> 직전까지)
    # 그룹 2: <figure> 태그의 내용물 (여는 태그의 > 다음부터 닫는 </figure> 직전까지)
    # 그룹 3: 닫는 </figure> 태그
    # 이 정규식은 figure_opening_tag, figure_content, figure_closing_tag를 분리하기 위함입니다.
    figure_pattern = re.compile(
        r"(<figure[^>]*>)(.*?)(<\/figure>)", re.IGNORECASE | re.DOTALL
    )

    def _normalize_and_replace_h6(match):
        # figure_opening_tag_original = match.group(1) # 원본 <figure ...> 태그
        figure_content = match.group(2)  # <figure>와 </figure> 사이의 내용
        # figure_closing_tag = match.group(3)     # </figure>

        # 1. 여는 <figure> 태그를 속성 없이 "<figure>"로 정규화
        normalized_figure_opening_tag = "<figure>"

        # 2. figure_content 내에서만 h6 -> figcaption 변경
        #    <h6 class="foo"> -> <figcaption class="foo">
        content_modified = re.sub(
            r"<h6([^>]*)>",
            r"<figcaption\1>",
            figure_content,
            flags=re.IGNORECASE,
        )
        content_modified = re.sub(
            r"</h6>", r"</figcaption>", content_modified, flags=re.IGNORECASE
        )

        # 정규화된 여는 태그, 수정된 내용, 닫는 태그를 조합
        # 가독성을 위해 줄바꿈 추가 (선택 사항)
        return f"{normalized_figure_opening_tag}\n{content_modified.strip()}\n</figure>"

    return figure_pattern.sub(_normalize_and_replace_h6, text)


def convert_internal_links_to_text(text: str) -> str:
    """
    내부 앵커 링크 <a href="#...">텍스트</a> 를 '텍스트'로 변경합니다.
    data-type="xref" 등 특정 속성을 가진 경우만 처리하거나 모든 #링크를 처리할 수 있습니다.
    """
    # 모든 #으로 시작하는 href를 가진 <a> 태그의 내용만 남김
    return re.sub(
        r"<a\s+(?:[^>]*?\s+)?href=\"#(?:[^\"]*)\"(?:[^>]*)>(.*?)<\/a>",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )


def normalize_blockquoted_headers(text: str) -> str:
    """
    인용구 내의 헤더(예: '> # 제목', '> ## 제목')를 모두 '> ### 제목' 형태로 변경합니다.
    """
    # 패턴 설명:
    # ^        : 각 줄의 시작 (re.MULTILINE 플래그 사용)
    # (>\s*)   : 그룹 1: '>' 문자 뒤에 0개 이상의 공백 (인용구 마커 부분 유지 위함)
    # (#{1,6}) : 그룹 2: '#' 문자가 1개에서 6개까지 있는 부분 (실제 헤더 레벨)
    # (\s+.*)  : 그룹 3: 헤더 표시 뒤의 공백들과 나머지 제목 텍스트 전체
    pattern = r"^(>\s*)(#{1,6})(\s+.*)$"

    # 치환: 그룹 1 (인용구 마커) + "###" + 그룹 3 (공백과 제목 텍스트)
    replacement = r"\1###\3"

    modified_text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    return modified_text


def convert_specific_img_tags_to_numbered_text(
    text: str, media_folder_name: str = "assets"
) -> str:
    """
    특정 HTML <img> 태그를 "숫자. " 형식의 텍스트로 변환합니다.
    예: <img src="./assets/1.png" alt="1" />  -> "1. "
    alt 속성의 숫자를 사용하며, src 경로의 숫자와 일치한다고 가정합니다.
    """
    # media_folder_name을 정규식에 사용하기 위해 이스케이프합니다.
    escaped_media_folder = re.escape(media_folder_name)

    # 패턴 설명:
    # <img\s+                                : <img 태그 시작과 최소 하나 이상의 공백
    # src="\./<escaped_media_folder>/\1\.png" : src 속성. \1은 alt에서 캡처된 숫자를 참조.
    # \s+alt="([0-9]+)"                       : alt="숫자" 속성. 숫자를 그룹 1로 캡처.
    # [^>]*?                                  : 다른 속성들 (비탐욕적 매칭)
    # \/?>                                    : 태그 닫힘 (/> 또는 >)
    #
    # 수정된 패턴: alt의 숫자를 기준으로 하고, src의 숫자도 일치하는지 확인 (더 안정적)
    # <img                                    : <img 태그 시작
    # \s+                                     : 하나 이상의 공백
    # (?:[^>]*?\s+)?                          : 다른 속성들 (선택적, 비탐욕적)
    # src="\.\/%s\/([0-9]+)\.png"             : src 속성, 파일명의 숫자를 그룹 1로 캡처
    # (?:[^>]*?\s+)?                          : 다른 속성들
    # alt="\1"                                : alt 속성의 값이 src의 숫자(그룹 1)와 일치해야 함
    # (?:[^>]*?)                              : 다른 속성들
    # \s*\/?>                                 : 태그 닫힘

    # 더 간단하고 명확한 접근: alt의 숫자를 가져오고, src 패턴도 대략적으로 일치하는지 확인
    # <img (속성들) alt="숫자" (속성들) src="./폴더/숫자.png" (속성들) />
    # 여기서는 alt의 숫자를 추출하고, src 패턴이 대략 일치하는지 확인하는 방식으로 접근합니다.
    # alt="숫자"에서 숫자를 캡처하는 것이 핵심입니다.

    pattern_str = (
        r"<img\s+"  # <img 시작과 공백
        r"(?:[^>]*?\s+)?"  # src 앞의 다른 속성들 (선택적)
        r'src="\.\/'
        + escaped_media_folder
        + r'\/[0-9]+\.png"'  # src 경로 패턴 확인
        r"(?:[^>]*?\s+)?"  # alt 앞의 다른 속성들 (선택적)
        r'alt="([0-9]+)"'  # alt="숫자" (숫자를 그룹 1로 캡처)
        r"(?:[^>]*?)"  # 나머지 속성들 (선택적)
        r"\s*\/?>\s+\n"  # 태그 닫힘 (/> 또는 >)
    )

    # 치환: 캡처된 숫자(그룹 1) + ". "
    replacement_str = r"\1. "

    modified_text = re.sub(
        pattern_str, replacement_str, text, flags=re.IGNORECASE
    )
    return modified_text


def convert_html_snippet_to_markdown(
    html_snippet: str,
    from_format: str = "html",
    to_format: str = "gfm",
) -> str:
    """
    주어진 HTML 조각을 Pandoc을 사용하여 지정된 마크다운 형식으로 변환합니다.
    테이블 셀 내부 리스트 평탄화를 위해 전용 Lua 필터를 사용하고,
    변환된 마크다운 테이블에서 Pandoc이 추가한 ID 속성을 제거합니다.
    """
    pandoc_cmd = ["pandoc", "--from", from_format, "--to", to_format]

    if os.path.exists(LUA_TABLE_FLATTENER_FILTER):
        pandoc_cmd.extend(["--lua-filter", LUA_TABLE_FLATTENER_FILTER])
    else:
        sys.stderr.write(
            f"Python Warning: Table flattener Lua filter not found at {LUA_TABLE_FLATTENER_FILTER}. Lists inside tables might not be flattened as intended.\n"
        )

    try:
        # <p></p> 태그를 미리 제거
        html_snippet = re.sub(
            r"<p>(.*?)</p>", r"\1", html_snippet, flags=re.DOTALL
        )
        process = subprocess.run(
            pandoc_cmd,
            input=html_snippet,
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode == 0:
            markdown_output = process.stdout.strip()
            markdown_output = re.sub(
                r"\s*\{\#([a-zA-Z0-9_.-]+)\}\s*$",
                "",
                markdown_output,
                flags=re.MULTILINE,
            )
            # 만약 속성이 여러 개일 경우 (예: {#id .class key=val}) 더 복잡한 정규식이 필요할 수 있으나,
            # 보통 테이블 ID는 단순 {#id} 형태입니다.
            # 좀 더 일반적인 Pandoc 속성 블록 제거 (주의해서 사용):
            # markdown_output = re.sub(r"\s*\{[^\}\n]+\}\s*$", "", markdown_output, flags=re.MULTILINE)
            return markdown_output
        else:
            sys.stderr.write(
                f"Python Warning: Pandoc failed to convert snippet (code {process.returncode}). Target format: {to_format}\n"
            )
            sys.stderr.write(f"Pandoc Stderr: {process.stderr[:500]}...\n")
            return html_snippet
    except FileNotFoundError:
        sys.stderr.write(
            "Python Error: pandoc command not found. Cannot convert HTML snippet to Markdown.\n"
        )
        return html_snippet
    except Exception as e:
        sys.stderr.write(
            f"Python Error during pandoc snippet conversion: {e}\n"
        )
        return html_snippet


# convert_tables_to_markdown 함수는 변경 없이 이 수정된 헬퍼 함수를 사용하게 됩니다.
def convert_tables_to_markdown(text: str) -> str:
    table_pattern = re.compile(
        r"<table[^>]*>.*?<\/table>", re.IGNORECASE | re.DOTALL
    )
    processed_count = 0

    def replace_with_markdown_table(match):
        nonlocal processed_count
        html_table = match.group(0)
        print("Original table:\n", html_table, "\n\n\n")
        markdown_table = convert_html_snippet_to_markdown(
            html_table, "html", "gfm"
        )
        print("Markdown table:\n", markdown_table, "\n\n\n")
        if markdown_table != html_table:
            processed_count += 1
        return markdown_table

    modified_text = table_pattern.sub(replace_with_markdown_table, text)
    return modified_text


def remove_reference_tags(text: str) -> str:
    return re.sub(r"{#[a-zA-Z0-9_]+}", "", text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python post_processor.py <markdown_file_path> [media_folder_name]",
            file=sys.stderr,
        )
        sys.exit(1)

    markdown_file_path = sys.argv[1]
    # media_folder_name은 스크립트 인자로 받거나, 없으면 기본값 사용
    current_media_folder = "assets"  # 기본값
    if len(sys.argv) > 2:
        current_media_folder = sys.argv[2]

    # print(f"Processing {markdown_file_path} with media folder '{current_media_folder}'", file=sys.stderr) # 디버깅용

    try:
        with open(markdown_file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: File not found {markdown_file_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file {markdown_file_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # 변환 순서가 중요할 수 있습니다.
    original_content = content

    # 1. 스마트 따옴표 변환 (Pandoc의 +smart 옵션이 이미 처리했을 수 있지만, 안전장치)
    content = convert_smart_quotes(content)

    # 2. 각주 정의 수정
    content = fix_footnote_definitions(content)

    # 3. Note/Tip/Warning/Caution을 Blockquote로 변환
    content = convert_h6_to_blockquote(content)

    # 4. 헤더 조정
    content = adjust_headers(content)

    # 5. 불필요 span 태그 제거
    content = remove_unwanted_spans(content)

    # 6. 각주 레퍼런스 포맷 수정
    content = convert_superscript_footnotes(content)

    # 7. 이미지 캡션 HTML 적용
    content = process_html_figures(content)

    # 8. 내부 앵커 링크 제거
    content = convert_internal_links_to_text(content)

    # 9. Blockquote 내 헤더 표준화
    content = normalize_blockquoted_headers(content)

    # 10. 번호 이미지 제거
    content = convert_specific_img_tags_to_numbered_text(content)

    # 11. 테이블 파싱
    content = convert_tables_to_markdown(content)

    # 12. 레퍼런스 태그 제거
    content = remove_reference_tags(content)

    # 변경 사항이 있을 때만 파일 쓰기 (선택 사항)
    if content != original_content:
        try:
            with open(markdown_file_path, "w", encoding="utf-8") as f:
                f.write(content)
            # print(f"File {markdown_file_path} has been updated.", file=sys.stderr) # 디버깅용
        except Exception as e:
            print(
                f"Error writing file {markdown_file_path}: {e}", file=sys.stderr
            )
            sys.exit(1)
    # else:
    # print(f"No changes made to {markdown_file_path}.", file=sys.stderr) # 디버깅용
