# About

This repo contains automation and helper scripts to convert [AK documentation](https://github.com/apache/kafka-site) from raw html source code to markdown. 

# How does it work?

AK documentation currently is stored in version control as raw html, css and js files. It makes use of sepcific `httpd` features such as ["Server Side Includes"](https://httpd.apache.org/docs/2.4/howto/ssi.html) and [Handlebars JS](https://handlebarsjs.com/) to render templated html content. 

To host this is a markdown based site, we will employ [Hugo](https://gohugo.io/) a static site generator from markdown, and [docsy](https://www.docsy.dev/) theme for structuring and styling the site.

## Pre-processing

`convert.py` does the job of going through the raw html, css, js, and other static content in the AK site and doing the first pass of converting it to markdown.

As part of this, we address the following:

- Sanitize input HTML. Some input HTML files contain characters such as `\w`, `\c` etc., that messes up regex search and subsitutue operations. Escape them correctly.
- There are a bunch of files where raw html code is placed under `<script/>` tags to be handled by HandleBars.js file in the original documentation. We will need to process them offline and convert them to raw HTML so that markdown conversion works.
- Process SSI tags. Wherever `#include virtual` SSI tags are present, insert a custom hugo short code `{{ <include-html >}} that will do the job of inserting the content of the specified html file safely at the location of reference.
- Convert sanitized and pre-processed raw HTML files to markdown.
- Add markdown front matter so that `hugo` can process them.
- There are a bunch of places in the original raw html source code where the heading levels are not used consistently, and in many cases contain manually coded numeric values in the headings. Uplevel headings where applicable and remove these numeric characters.

Clone the [AK documentation](https://github.com/apache/kafka-site) and use this as the input for this phase. 

## Post-processing

Converting the raw html files to markdown is only half the work. These files will further need to be processed so that we can rearrange and structure them for better readability, maintainability.

`post_process.py` does this job. It uses an externalized declarative policy as specified in `process.yaml` to do this work.

- There are multiple versions of the documentation stored in this repo. 
- Each version has several sections that need to be organized and restrucutred.
- As such, the policy defines what these sections are. 
- We support a few strategies to organize these sections:
  - `arrange`. Arranges the files from pre-process phase in the order specified. Automatically assigns weights (so that they are ordered as we need them) and takes care of renaming, placing the files in the right location etc.,
  - `split_markdown_by_heading`. There are some very large files in the code base and for better readability/maintainability, we would want to split them into different files in a given section. Collect the content b/w specified heading levels and automatically generate intermediate files, arrange them.
- Go through `links` in the markdown files in the pre-process phase and modify them as specified in `link_updates` section. Add `prefix`, `replace` or `subtitute` part of the link.
- Move `generated` and `javadoc` files into `static` folder so that we don't have to convert them into markdown, but instead use the `include-html` shortcode to pull in the content from HTML. 

