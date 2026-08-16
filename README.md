# DownVas - Canvas Downloader CLI

DownVas is a Command Line Interface (CLI) tool written in Python to interactively and systematically download course files hosted on Canvas LMS.

<img width="509" height="502" alt="image" src="https://github.com/user-attachments/assets/45a87fa1-866c-46b8-9a9b-c8431f63cf4c" />



## Key Features

- **Token Authentication**: Securely and easily configure your Canvas URL and access token (API Token).
- **Multi-language Support (i18n)**: Interface available in English and Spanish, configurable through the wizard.
- **Hierarchical Exploration**: Visualize all your course content in a tree structure (Folders, Modules, and Files) with distinctive colors by file type, entirely from your terminal.
- **Multiple Download Options**:
  - Download a specific file (by ID, name, or tree index).
  - Download a queue of manually selected files.
  - Download all files with a specific extension (e.g., `.pdf`, `.pptx`).
  - Download all course files at once.
  - Download all files from a specific section or module.
- **Robust Downloads**: 
  - Downloads are chunked and include a detailed progress bar with transfer speed and estimated time remaining.
  - Temporary files (`.part`) are used during transfers to prevent corrupted files if the connection drops.
  - Native support to automatically skip files that have already been downloaded locally.
- **Automatic Organization**: Downloaded files are automatically saved respecting the course's original folder and module structure.

## Requirements

- Python 3.10+ (tested on 3.11)
- Dependencies (can be installed via `requirements.txt`):
  - `requests==2.34.2`
  - `rich==15.0.0`
  - `pydantic==2.13.4`
  - `python-dotenv==1.2.2`

## Installation

1. Clone or download this repository.
2. Create and activate a virtual environment (optional but recommended):
   ```bash
   python -m venv .venv
   ```
   - **Linux/macOS**: `source .venv/bin/activate`
   - **Windows**: `.venv\Scripts\activate`
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

To start the wizard and the main menu, simply run:

```bash
python main.py
```

### First Launch (Configuration)
If this is your first time running it, DownVas will start an interactive wizard asking for:
1. **Canvas LMS URL** (e.g., `https://canvas.instructure.com` or your university's domain).
2. **Access token** (can be generated from Canvas -> Account -> Settings -> New Access Token).
3. **Interface language** (select `en` for English or `es` for Spanish).
4. **Local download folder** (the path where you want to save the courses, e.g., `./Downloads` or `./Descargas` adapting to the language).

*These details will be stored locally in a `.env` file.*

### Supported Course ID / URL Inputs

The course prompt accepts a numeric ID or any of the following URL formats:

- **Course ID**: `107487`
- **Course URL**: `https://canvas.uautonoma.cl/courses/107487`
- **File URL**: `https://canvas.uautonoma.cl/courses/107487/files/8092477` — loads the course and also resolves that specific file, even if it is not in the tree yet.
- **Module item URL**: `https://canvas.uautonoma.cl/courses/107487/modules/items/4024443` — loads the course and resolves the contents of that module item so its files can be listed and downloaded. Supported item types:
  - `Page` — reads the page body and lists every file linked in it.
  - `File` — a direct Canvas file.
  - `Assignment`, `Discussion` and `Quiz` — scans the description/message HTML plus the file attachments.
  - `ExternalUrl` / `ExternalTool` / `SubHeader` — no Canvas-hosted files are extracted.

> Example: a module page like `.../courses/107487/modules/items/4024443` (`type: Page`) lists its linked files under "Pages → <page title>", and they download like any other course file.

### Main Menu
Once configured, after entering a course ID (or full URL), you will be presented with an interactive menu with the following options:

1. **View course listing**: Prints the hierarchical structure of files, folders, and modules.
2. **Refresh course information**: Reloads the file tree from the server.
3. **Download a single file**: Selects and downloads a single file.
4. **Download multiple files**: Allows you to queue files and download them in a batch.
5. **Download files by extension (e.g.: .pdf)**: Filters and downloads all `.pdf`, `.ppt`, etc.
6. **Download all course files**: Downloads the complete course preserving the folder hierarchy.
7. **Download by section**: Downloads all files from a specific module or folder.
8. **Reassign credentials**: Configuration wizard option.
9. **Switch course**: Lets you enter a new ID to explore another course.
10. **Exit**

## Directory Structure

- `main.py`: Application entry point and interactive menu controller.
- `src/`
  - `cli.py`: Handlers for each menu option (configuration wizard, downloads, refresh, change course/URL/token).
  - `core.py`: Definitions for common errors, utilities (e.g., URL validation) and configuration loading (Settings).
  - `courses.py`: Canvas API client, paginated requests handling, and hierarchical tree generation.
  - `downloader.py`: Dedicated service for chunked file downloading, `.part` file handling, and progress bar interface.
  - `i18n.py`: Internationalization engine to translate the interface.
  - `theme.py`: Centralized definition of the terminal interface visual theme (colors and styles).
- `locales/`: Translation files and compiled dictionaries (`.po` and `.mo`).
- `.env`: (Auto-generated) Environment variables file for storing credentials.
