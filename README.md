# Epub to Markdown Converter

Converts an EPUB file to GFM Markdown with advanced processing. I used Gemini 2.5 Pro to write the shell and Lua scripts, and I wrote the post-processing scripts myself.

> [!Warning]
> It is intended for personal use only and is not actively maintained.

## Usage

First of all, make sure the following dependencies are installed.

```text
- pandoc
- awk
- realpath (or readlink -f)
- sed
- tput
```

After cloning this repository, run the below command in your directory.

```bash
./scripts/epub-to-markdown.sh --split "^## " --remove-span-class "label,keep-together" book.epub ./out
```
### Arguments:
  - `<input_epub_file>`: Path to the input EPUB file.  
  - `<output_directory>`: Path to the directory where output files will be saved.

### Options:
  - `--split REGEX`
    - *Optional*. Split the output Markdown file using awk.
  - `--remove-span-class "CLASS1,..."`
    - *Optional*. Remove <span> tags with specified classes.
  - `--assets-name NAME` 
    - *Optional*. Set the media folder name (default: `assets`).

## Advanced Usage

### Post-processing with Python scripts

You can use `post_processor.py` to post-process the converted markdown. It does things that are hard to apply with `pandoc`. The Python script I currently provide utilises a table processing script written in Lua (`table_flattener.lua`).

> [!Tip]
> If you find that your tables are not converting as you want when converting your Epub, you should try the following command to see what HTML tags your tables are converting to.
> ```
> pandoc <input_file> -o native_output.txt
> ```
> If the table converted to HTML tags has `<p></p>` tags, you can remove them and then use `pandoc` to convert the HTML-tagged table to markdown.

