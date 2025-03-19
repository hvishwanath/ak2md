# About

This repo contains automation and helper scripts to convert [AK documentation](https://github.com/apache/kafka-site) from raw html source code to markdown. 

# How does it work?

AK documentation currently is stored in version control as raw html, css and js files. It makes use of specific `httpd` features such as ["Server Side Includes"](https://httpd.apache.org/docs/2.4/howto/ssi.html) and [Handlebars JS](https://handlebarsjs.com/) to render templated html content. 

To host this is a markdown based site, we will employ [Hugo](https://gohugo.io/) a static site generator from markdown, and [docsy](https://www.docsy.dev/) theme for structuring and styling the site.

## Automated End-to-End Workflow

The project now includes a fully automated, end-to-end workflow system that handles the entire conversion process from cloning the Kafka site repository to generating the final markdown structure for Hugo.

### Workflow Architecture

The workflow is broken down into composable, idempotent stages:

1. **Clone Stage** - Clones/updates the Kafka website repository
2. **Pre-processing Stage** - Converts raw HTML to intermediate markdown
3. **Post-processing Stage** - Restructures markdown for better organization
4. **Validation Stage** - Verifies the output meets expectations

Each stage is further broken down into individual steps that can be customized, reordered, or selectively applied.

### Using the Workflow

```bash
# Basic usage
python workflow.py --workspace ./my_workspace

# Start from a specific stage
python workflow.py --workspace ./my_workspace --start-stage pre-process

# Enable debug logging
python workflow.py --workspace ./my_workspace --debug

# Skip validation stage
python workflow.py --workspace ./my_workspace --skip-validation
```

### Workflow Components

- **workflow.py** - Main entry point and workflow orchestration
- **workflow_steps.py** - Fine-grained steps and processors for each stage
- **process.yaml** - Configuration for document sections and processing rules

### Features

- **Composable** - Each stage and step can run independently
- **Idempotent** - Safe to run multiple times
- **Debuggable** - Detailed logging and clear error messages
- **Configurable** - Easy to customize through process.yaml
- **Extensible** - New steps can be easily added to the registry

### Static Content Handling

The workflow automatically handles static content such as:

- **Images** - Both root level and version-specific image directories
- **Diagrams** - Diagram files used in documentation
- **Logos** - Brand assets and logos
- **Generated Content** - Auto-generated documentation files
- **JavaDoc** - Java API documentation

Static directories are:
1. Identified via the `static_dirs` list in `process.yaml`
2. Copied to the appropriate location in the `static` output directory
3. Referenced correctly in markdown via the link updates in `process.yaml`
4. Validated to ensure they exist and contain files

## Pre-processing

Process directories and files, going through the raw html, css, js, and other static content in the AK site and doing the first pass of converting it to markdown.

As part of this, we address the following:

- Sanitize input HTML. Some input HTML files contain characters such as `\w`, `\c` etc., that messes up regex search and subsitutue operations. Escape them correctly.
- There are a bunch of files where raw html code is placed under `<script/>` tags to be handled by HandleBars.js file in the original documentation. We will need to process them offline and convert them to raw HTML so that markdown conversion works.
- Process SSI tags. Wherever `#include virtual` SSI tags are present, insert a custom hugo short code `{{ <include-html >}} that will do the job of inserting the content of the specified html file safely at the location of reference.
- Convert sanitized and pre-processed raw HTML files to markdown.
- Add markdown front matter so that `hugo` can process them.
- There are a bunch of places in the original raw html source code where the heading levels are not used consistently, and in many cases contain manually coded numeric values in the headings. Uplevel headings where applicable and remove these numeric characters.

## Post-processing

Converting the raw html files to markdown is only half the work. These files will further need to be processed so that we can rearrange and structure them for better readability, maintainability.

Based on the rules defined in `process.yaml`: 

- There are multiple versions of the documentation stored in this repo. 
- Each version has several sections that need to be organized and restrucutred.
- As such, the policy defines what these sections are. 
- Supports a few strategies to organize these sections:
  - `arrange`. Arranges the files from pre-process phase in the order specified. Automatically assigns weights (so that they are ordered as we need them) and takes care of renaming, placing the files in the right location etc.,
  - `split_markdown_by_heading`. There are some very large files in the code base and for better readability/maintainability, we would want to split them into different files in a given section. Collect the content b/w specified heading levels and automatically generate intermediate files, arrange them.
- Go through `links` in the markdown files in the pre-process phase and modify them as specified in `link_updates` section. Add `prefix`, `replace` or `subtitute` part of the link.
- Move `generated` and `javadoc` files into `static` folder so that we don't have to convert them into markdown, but instead use the `include-html` shortcode to pull in the content from HTML. 

## Installation

```bash
# Clone the repository
git clone https://github.com/hvishwanath/ak2md.git
cd ak2md

# Install dependencies
pip install -r requirements.txt

# Run the workflow
python workflow.py
```

