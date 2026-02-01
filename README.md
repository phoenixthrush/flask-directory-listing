# flask-directory-listing

Flask app that replicates Apache-style directory listings. Supports file uploads and folder downloads as ZIP archives.

## Installation

```bash
pip install flask-directory-listing
```

## Usage

```bash
flask-directory-listing \
  --root /path/to/serve \
  --host 0.0.0.0 \
  --port 8080 \
  --apache-style \
  --debug
```

Flags:

- `--root` directory to serve (default: `src/flask_directory_listing/apache/share`)
- `--host` listen address (default: `0.0.0.0`)
- `--port` listen port (default: `8080`)
- `--apache-style` enable mixed sorting like Apache (otherwise directories first)
- `--debug` enable Flask debug mode

Alternate invocation:

```bash
flask_directory_listing [flags]
```

Features:

- Apache-like index table with sorting links and icons
- Directory download as ZIP (`?download=<folder>`) links beside folders
- Drag-and-drop uploads, including nested folders
- Hidden files are ignored; path traversal is blocked
