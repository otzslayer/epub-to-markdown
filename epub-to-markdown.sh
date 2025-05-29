#!/bin/bash

# ==============================================================================
# epub-to-markdown.sh
# ==============================================================================
# Description: Converts EPUB to GFM Markdown. Uses advanced Lua filters.
#              Uses sed for post-processing.
# Author:      Jay Han with Gemini 2.5 Pro
# Date:        2025-05-27
# Requires:    pandoc, awk, bash, realpath (or readlink -f), sed, tput
# ==============================================================================

# --- Colors & Logging ---

if tput setaf 1 &>/dev/null; then
  RESET=$(tput sgr0)
  RED=$(tput setaf 1)
  GREEN=$(tput setaf 2)
  YELLOW=$(tput setaf 3)
  BLUE=$(tput setaf 4)
  CYAN=$(tput setaf 6)
  BOLD=$(tput bold)
else
  RESET=""
  RED=""
  GREEN=""
  YELLOW=""
  BLUE=""
  CYAN=""
  BOLD=""
fi

# Logging Functions with Timestamp
log_info() {
  local timestamp
  timestamp=$(date +"%Y-%m-%d %H:%M:%S")
  echo -e "${BLUE}${BOLD}[${timestamp}] [INFO]${RESET}  $1"
}
log_success() {
  local timestamp
  timestamp=$(date +"%Y-%m-%d %H:%M:%S")
  echo -e "${GREEN}${BOLD}[${timestamp}] [SUCCESS]${RESET} $1"
}
log_warn() {
  local timestamp
  timestamp=$(date +"%Y-%m-%d %H:%M:%S")
  echo -e "${YELLOW}${BOLD}[${timestamp}] [WARN]${RESET}  $1"
}
log_error() {
  local timestamp
  timestamp=$(date +"%Y-%m-%d %H:%M:%S")
  echo -e "${RED}${BOLD}[${timestamp}] [ERROR]${RESET} $1" >&2 # Errors to stderr
}

# --- Functions ---

usage() {
  cat <<EOF >&2
Usage: $(basename "$0") [OPTIONS] <input_epub_file> <output_directory>

Converts an EPUB file to GFM Markdown with advanced processing.

Arguments:
  <input_epub_file>   Path to the input EPUB file.
  <output_directory>  Path to the directory where output files will be saved.

Options:
  --split REGEX       Optional. Split the output Markdown file using awk.
  --remove-span-class "CLASS1,..."
                      Optional. Remove <span> tags with specified classes.
  --assets-name NAME  Optional. Set the media folder name (default: assets).
  -h, --help          Display this help message and exit.

Example:
  $(basename "$0") --split "^## " --remove-span-class "label,keep-together" book.epub ./out

IMPORTANT: Run this script with 'bash' or './$(basename "$0")', NOT 'sh'.
EOF
  exit 1
}

command_exists() { command -v "$1" >/dev/null 2>&1; }

get_abs_path() {
  local target_path="$1"
  local abs_path=""
  if [ ! -e "$target_path" ]; then
    log_error "Path does not exist: $target_path"
    return 1
  fi
  if command_exists realpath; then
    abs_path=$(realpath "$target_path")
  elif command_exists readlink; then
    abs_path=$(readlink -f "$target_path")
  else
    log_error "Neither 'realpath' nor 'readlink -f' found."
    exit 10
  fi
  echo "$abs_path"
}

# --- Argument Parsing ---

SPLIT_REGEX=""
REMOVE_SPAN_CLASS=""
INPUT_EPUB=""
OUTPUT_DIR=""
MEDIA_FOLDER_NAME="assets"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PYTHON_PROCESSOR_SCRIPT="${SCRIPT_DIR}/post_processor.py"

while [[ $# -gt 0 ]]; do
  case "$1" in
  --split)
    if [[ -z "$2" || "$2" == -* ]]; then
      log_error "--split requires a REGEX."
      usage
    fi
    SPLIT_REGEX="$2"
    shift 2
    ;;
  --remove-span-class)
    if [[ -z "$2" || "$2" == -* ]]; then
      log_error "--remove-span-class requires a CLASS list."
      usage
    fi
    REMOVE_SPAN_CLASS="$2"
    shift 2
    ;;
  --assets-name)
    if [[ -z "$2" || "$2" == -* ]]; then
      log_error "--assets-name requires a NAME."
      usage
    fi
    MEDIA_FOLDER_NAME="$2"
    shift 2
    ;;
  -h | --help) usage ;;
  -*)
    log_error "Unknown option: $1"
    usage
    ;;
  *)
    if [[ -z "$INPUT_EPUB" ]]; then
      INPUT_EPUB="$1"
    elif [[ -z "$OUTPUT_DIR" ]]; then
      OUTPUT_DIR="$1"
    else
      log_error "Too many arguments."
      usage
    fi
    shift 1
    ;;
  esac
done

# --- Input Validation ---

if ! command_exists pandoc; then
  log_error "pandoc is not installed."
  exit 2
fi
if ! command_exists sed; then
  log_error "sed is not installed."
  exit 2
fi
if [[ -n "$SPLIT_REGEX" ]] && ! command_exists awk; then
  log_error "awk is not installed."
  exit 2
fi
if [[ -z "$INPUT_EPUB" || -z "$OUTPUT_DIR" ]]; then
  log_error "Input EPUB and Output Directory required."
  usage
fi
if [[ ! -f "$INPUT_EPUB" ]]; then
  log_error "Input file not found: $INPUT_EPUB"
  exit 3
fi
if ! command_exists tput; then
  log_warn "tput not found. Colors will not be used."
  RESET=""
  RED=""
  GREEN=""
  YELLOW=""
  BLUE=""
  CYAN=""
  BOLD=""
fi
PYTHON_CMD=$(command -v python3 || command -v python)
if ! command_exists "$PYTHON_CMD"; then
  log_warn "Python (python3 or python) is not installed. Python post-processing will be skipped."
  PYTHON_CMD=""
fi
if [[ -n "$PYTHON_CMD" && ! -f "$PYTHON_PROCESSOR_SCRIPT" ]]; then
  log_warn "Python post-processor script ($PYTHON_PROCESSOR_SCRIPT) not found. Skipping Python post-processing."
  PYTHON_CMD="" # Python 처리 비활성화
fi

# --- Main Logic ---

log_info "Starting EPUB to Markdown conversion..."
mkdir -p "$OUTPUT_DIR" || {
  log_error "Could not create output directory: $OUTPUT_DIR"
  exit 4
}

INPUT_EPUB_ABS=$(get_abs_path "$INPUT_EPUB") || exit 6
OUTPUT_DIR_ABS=$(get_abs_path "$OUTPUT_DIR") || exit 6

EPUB_BASENAME=$(basename "$INPUT_EPUB_ABS")
MD_FILENAME="${EPUB_BASENAME%.*}.md"
MD_BASENAME_NO_EXT="${MD_FILENAME%.*}"

log_info "Input EPUB: $INPUT_EPUB_ABS"
log_info "Output Directory: $OUTPUT_DIR_ABS"
log_info "Output Markdown: $OUTPUT_DIR_ABS/$MD_FILENAME"
log_info "Media Folder: $MEDIA_FOLDER_NAME"

# --- Lua 필터 파일 생성 ---
LUA_FILTER_FILE=$(mktemp -t lua_filter_XXXXXX.lua)
trap "log_info 'Cleaning up temporary files...'; rm -f '$LUA_FILTER_FILE'" EXIT
LUA_FILTER_FILE_ABS=$(get_abs_path "$LUA_FILTER_FILE") || {
  log_error "Error getting temp file path."
  exit 6
}

log_info "Creating Lua filter in $LUA_FILTER_FILE_ABS"
cat <<EOF >"$LUA_FILTER_FILE_ABS"
-- RawBlock: HTML RawBlock 선택적 처리
function RawBlock (el)
  if el.format:match 'html' then
    if el.text:match("^<figure") or el.text:match("^<table") then
      -- <figure> 또는 <table> 블록은 HTML 그대로 유지
      return el 
    elseif el.text:match("^<aside") then
      -- <aside ...> 로 시작하는 RawBlock은 다시 파싱하여 구조화된 요소로 변환
      -- 이후 Div 또는 Aside 필터가 처리할 수 있도록 함
      return pandoc.read(el.text, 'html').blocks
    else
      -- 그 외 다른 HTML RawBlock은 내용까지 완전히 제거
      return pandoc.Blocks{} 
    end
  end
  return el -- HTML 형식이 아니면 그대로 반환
end

-- Div 처리
function Div (el)
  local is_sidebar_div = false
  if el.attributes then
    if el.attributes['data-type'] == 'sidebar' or el.attributes['epub:type'] == 'sidebar' then
      is_sidebar_div = true
    end
  end
  if el.classes then
    if el.classes:includes("sidebar") or el.classes:includes("aside") then
      is_sidebar_div = true
    end
  end

  if is_sidebar_div then
    -- 사이드바/어사이드로 판단되는 Div는 내용을 인용구로 변환
    return pandoc.BlockQuote(el.content) 
  else
    -- 다른 일반적인 Div는 내용만 남김 (껍데기 제거)
    return el.content 
  end
end

-- Aside 처리
function Aside (el)
  -- 모든 Aside 요소를 인용구로 변환
  -- 특정 조건의 Aside만 변환하려면 여기에 if 조건 추가
  return pandoc.BlockQuote(el.content)
end

-- CodeBlock 처리 (기존과 동일)
function CodeBlock (el)
  local lang = el.attributes['code-language']
  if lang and #el.classes == 0 then
    table.insert(el.classes, 1, lang)
    el.attributes['code-language'] = nil
  end
  return el
end

-- Superscript 처리 (각주 변환, 기존과 동일)
function Superscript (el)
  if #el.content == 1 and el.content[1].t == "Link" then
    local link = el.content[1]
    if link.attributes['data-type'] == 'noteref' then
      local link_text = pandoc.utils.stringify(link.content)
      local num = link_text:match("^[0-9]+$") 
      if num then return pandoc.RawInline('markdown', '[^' .. num .. ']') end
    end
  end
  return el
end

-- Blocks 필터 (이미지+H6 -> HTML Figure, 기존과 동일)
-- 이 필터는 figure/table이 이미 RawBlock으로 처리된 경우에는 해당되지 않음
function Blocks(blocks)
  local new_blocks = pandoc.Blocks{}
  local i = 1
  while i <= #blocks do
    local current_block = blocks[i]
    local next_block = (i < #blocks) and blocks[i+1] or nil 
    local image_details = nil

    if current_block.t == "Para" and #current_block.content == 1 and current_block.content[1].t == "Image" then
      image_details = current_block.content[1]
    elseif current_block.t == "Image" then
      image_details = current_block
    end

    if image_details and next_block and next_block.t == "Header" and next_block.level == 6 then
      local img_src = image_details.src or "" 
      local img_alt_inlines = image_details.caption 
      local img_alt = ""
      if img_alt_inlines then
        img_alt = pandoc.utils.stringify(img_alt_inlines)
      end
      img_alt = img_alt:gsub('"', '&quot;')

      local caption_html_fragment = ""
      local caption_inlines = next_block.content 
      if caption_inlines and #caption_inlines > 0 then
          local caption_doc = pandoc.Pandoc(pandoc.Plain(caption_inlines))
          local raw_caption_html = pandoc.write(caption_doc, "html")
          if type(raw_caption_html) == "string" then
              caption_html_fragment = raw_caption_html:gsub("^<p>", ""):gsub("</p>\n?$", "")
          else
              caption_html_fragment = pandoc.utils.stringify(caption_inlines)
              caption_html_fragment = caption_html_fragment:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;")
          end
      end
      
      local figure_html = string.format(
        "<figure>\n  <img src=\"%s\" alt=\"%s\" />\n  <figcaption>%s</figcaption>\n</figure>", -- h6 -> figcaption
        img_src, img_alt, caption_html_fragment
      )
      new_blocks:insert(pandoc.RawBlock("html", figure_html))
      i = i + 2 
    else
      new_blocks:insert(current_block)
      i = i + 1
    end
  end
  return new_blocks
end
EOF

if [[ -n "$REMOVE_SPAN_CLASS" ]]; then
  log_info "Adding Span filter to remove classes: $REMOVE_SPAN_CLASS"
  LUA_CLASSES_STR=$(echo "$REMOVE_SPAN_CLASS" | sed -e 's/,/","/g' -e 's/^/"/' -e 's/$/"/')
  cat <<EOF >>"$LUA_FILTER_FILE_ABS"
local classes_to_remove = { $LUA_CLASSES_STR }
function Span (el)
  for _, class_to_check in ipairs(classes_to_remove) do
    if el.classes:includes(class_to_check) then return el.content end
  end
  return el
end
EOF
fi

# --- Pandoc Command Setup ---
PANDOC_ARGS=("$INPUT_EPUB_ABS" -o "$MD_FILENAME" --extract-media . --wrap=none -t gfm+raw_html+alerts+footnotes+hard_line_breaks+smart)
PANDOC_ARGS+=("--lua-filter" "$LUA_FILTER_FILE_ABS")

# --- Pandoc 실행 ---
log_info "Changing directory to $OUTPUT_DIR_ABS"
pushd "$OUTPUT_DIR_ABS" >/dev/null
log_info "Running pandoc..."
pandoc "${PANDOC_ARGS[@]}"
PANDOC_STATUS=$?

if [[ $PANDOC_STATUS -ne 0 ]]; then
  log_error "Pandoc conversion failed."
  popd >/dev/null
  exit 5
fi

if [ -d "media" ]; then
  log_info "Renaming 'media' folder to '$MEDIA_FOLDER_NAME'..."
  if [ -d "$MEDIA_FOLDER_NAME" ]; then
    cp -r media/* "$MEDIA_FOLDER_NAME/" 2>/dev/null || mv media "$MEDIA_FOLDER_NAME"
    rm -rf media
  else
    mv "media" "$MEDIA_FOLDER_NAME"
  fi
fi
log_success "Conversion successful: $MD_FILENAME"
log_info "Images (if any) extracted to $MEDIA_FOLDER_NAME/"

# --- Python 후처리 ---
if [[ -n "$PYTHON_CMD" ]]; then
  log_info "Running Python post-processing script..."
  "$PYTHON_CMD" "$PYTHON_PROCESSOR_SCRIPT" "$MD_FILENAME" "$MEDIA_FOLDER_NAME"
  PY_STATUS=$?
  if [[ $PY_STATUS -ne 0 ]]; then
    log_error "Python post-processing script failed with status $PY_STATUS."
  else
    log_info "Python post-processing finished."
  fi
fi
# --- SED 후처리 ---
# 이미지 앵커 링크 처리
log_info "Processing multi-line image anchor links..."
sed -i.bak -E 's#^\[!\[([0-9]*)\]\(([^)]*)\)\]\(([^)]*)\)\s*#\1\. #g' "$MD_FILENAME"
# .bak 파일 정리
rm -f "$MD_FILENAME.bak"
log_info "Post-processing finished."
# --- SED 후처리 끝 ---

# --- Splitting Logic (Using awk) ---
if [[ -n "$SPLIT_REGEX" ]]; then
  log_info "Splitting file $MD_FILENAME using awk with regex: $SPLIT_REGEX"
  awk -v pattern="$SPLIT_REGEX" -v base="$MD_BASENAME_NO_EXT" '
    BEGIN { filenum = 0; outfile = sprintf("%s_%03d.md", base, filenum); }
    ($0 ~ pattern && NR > 1) { filenum++; outfile = sprintf("%s_%03d.md", base, filenum); }
    { print $0 > outfile; }
  ' "$MD_FILENAME"
  AWK_STATUS=$?
  if [[ $AWK_STATUS -eq 0 ]]; then
    log_success "File split successfully."
    log_info "Removing original merged file: $MD_FILENAME"
    rm "$MD_FILENAME"
  else
    log_error "awk processing failed."
    log_warn "The original file $MD_FILENAME has been kept."
  fi
fi

popd >/dev/null
log_success "Script finished."
exit 0
