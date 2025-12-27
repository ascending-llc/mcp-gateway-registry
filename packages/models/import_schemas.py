#!/usr/bin/env python3
"""
JSON Schema to Beanie ODM Model Generator

This script converts JSON schemas to Python Beanie Document models for Motor + Beanie ODM.
Supports two modes: Local (read from local files) and Remote (download from GitHub Release).

Usage:
    # Local mode - convert from local JSON files
    python import-schemas.py --mode local --input-dir DIR --files FILE1 FILE2 ... --output-dir DIR

    # Remote mode - download from GitHub Release
    python import-schemas.py --mode remote --tag VERSION --files FILE1 FILE2 ... --output-dir DIR

Examples:
    # Local mode - convert from local directory (recommended for development)
    python import-schemas.py --mode local --input-dir ./dist/json-schemas --files user.json token.json --output-dir ./models

    # Local mode - batch conversion
    python import-schemas.py --mode local --input-dir ./dist/json-schemas --files user.json token.json mcpServer.json session.json --output-dir ./app/models

    # Remote mode - download from GitHub Release (private repository)
    python import-schemas.py --mode remote --tag asc0.4.0 --files user.json token.json --output-dir ./models --token GitHub_Token --repo ascending-llc/jarvis-api

    # Remote mode - public repository (--mode remote is default, can be omitted)
    python import-schemas.py --tag asc0.4.0 --files user.json token.json --output-dir ./models

Features:
    - No third-party dependencies (uses only Python stdlib)
    - Local mode: Fast, no network required, ideal for development
    - Remote mode: Download from GitHub Release, ideal for CI/CD
    - Generates Beanie Document classes with proper type hints
    - Handles indexes, timestamps, references (Link), and nested documents
    - Cross-platform compatible (Windows/Linux/macOS)
"""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone


class BeanieModelGenerator:
    """Generate Beanie ODM models from JSON Schema"""

    # Type mapping from JSON Schema to Python types
    TYPE_MAPPING = {
        'string': 'str',
        'number': 'float',
        'integer': 'int',
        'boolean': 'bool',
        'array': 'List',
        'object': 'Dict',
    }

    def __init__(self, output_dir: str, github_repo: str = "ascending-llc/jarvis-api",
                 github_token: Optional[str] = None):
        self.output_dir = Path(output_dir)
        self.generated_dir = self.output_dir / '_generated'
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.github_repo = github_repo
        self.github_token = github_token
        self.imported_types = set()

    def load_local_schema(self, input_dir: str, filename: str) -> Dict[str, Any]:
        """
        Load JSON schema from local directory

        Args:
            input_dir: Local directory containing JSON schema files
            filename: JSON schema filename

        Returns:
            Parsed JSON schema dictionary
        """
        if not filename.endswith('.json'):
            filename += '.json'

        schema_path = Path(input_dir) / filename

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)

        return schema

    def download_schema(self, tag: str, filename: str) -> Dict[str, Any]:
        """
        Download JSON schema from GitHub Release using API.

        For private repositories, direct download links return 404.
        We need to use GitHub API to get asset ID and then download.
        """
        if not filename.endswith('.json'):
            filename += '.json'

        try:
            owner, repo = self.github_repo.split('/')
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"

            headers = {
                'User-Agent': 'Jarvis-Schema-Downloader',
                'Accept': 'application/vnd.github.v3+json'
            }

            if self.github_token:
                headers['Authorization'] = f'token {self.github_token}'

            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")
                release_data = json.loads(response.read().decode('utf-8'))

            asset_id = None
            for asset in release_data.get('assets', []):
                if asset['name'] == filename:
                    asset_id = asset['id']
                    break

            if not asset_id:
                available_files = [a['name'] for a in release_data.get('assets', [])]
                raise Exception(
                    f"File '{filename}' not found in release {tag}. "
                    f"Available files: {', '.join(available_files) if available_files else 'none'}"
                )

            download_url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}"
            headers['Accept'] = 'application/octet-stream'

            req = urllib.request.Request(download_url, headers=headers)
            with urllib.request.urlopen(req) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")
                content = response.read().decode('utf-8')
                schema = json.loads(content)
                return schema

        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise Exception(f"Release '{tag}' or file '{filename}' not found") from e
            elif e.code == 401:
                raise Exception(f"Invalid or missing GitHub token") from e
            raise
        except Exception:
            raise

    def generate_model(self, schema: Dict[str, Any]) -> tuple[str, str]:
        """Generate Python Beanie model code from JSON schema
        
        Returns:
            tuple: (model_code, class_name)
        """
        self.imported_types = set()

        title = schema.get('title', 'Document')
        collection_name = schema.get('x-collection', title.lower() + 's')
        properties = schema.get('properties', {})
        required_fields = schema.get('required', [])
        indexes = schema.get('x-indexes', [])
        has_timestamps = schema.get('x-timestamps', False)

        field_level_indexes = self._collect_field_indexes(properties)

        lines = []
        lines.append(f'class {title}(Document):')
        lines.append('    """')
        lines.append(f'    {title} Model')
        lines.append('    ')

        if 'x-generated' in schema:
            gen_info = schema['x-generated']
            lines.append(f"    Generated from: {gen_info.get('source_file', 'N/A')}")
            lines.append(f"    Schema version: {gen_info.get('version', 'N/A')}")
            lines.append(f"    Generated at: {gen_info.get('timestamp', 'N/A')}")

        lines.append('    """')
        lines.append('')

        field_lines = []
        for field_name, field_def in properties.items():
            field_line = self._generate_field(field_name, field_def, field_name in required_fields)
            if field_line:
                field_lines.append(field_line)

        if not field_lines:
            field_lines.append('    pass')

        lines.extend(field_lines)

        lines.append('')
        lines.append('    class Settings:')
        lines.append(f'        name = "{collection_name}"')

        if has_timestamps:
            lines.append('        use_state_management = True')

        all_indexes = field_level_indexes + indexes
        if all_indexes:
            lines.append('')
            lines.append('        indexes = [')
            for idx in all_indexes:
                idx_line = self._generate_index(idx)
                if idx_line:
                    lines.append(f'            {idx_line},')
            lines.append('        ]')

        imports = self._generate_imports(has_timestamps)

        return imports + '\n\n' + '\n'.join(lines), title

    def _collect_field_indexes(self, properties: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Collect field-level index definitions from x-index and x-unique"""
        field_indexes = []

        for field_name, field_def in properties.items():
            if field_def.get('x-unique'):
                field_indexes.append({
                    'fields': {field_name: 1},
                    'unique': True
                })
            elif field_def.get('x-index'):
                field_indexes.append({
                    'fields': {field_name: 1}
                })

        return field_indexes

    def _generate_field(self, field_name: str, field_def: Dict[str, Any], is_required: bool) -> str:
        """Generate a single field definition"""
        field_type = self._get_python_type(field_def)
        field_attrs = []
        comments = []

        # Handle reference fields - use Link type for better Beanie integration
        ref_model = field_def.get('x-ref')
        if ref_model and field_type == 'PydanticObjectId':
            # Use Link type for references
            field_type = f'Link["{ref_model}"]'
            self.imported_types.add('Link')
            comments.append(f'references {ref_model} collection')
        elif ref_model:
            comments.append(f'ref: {ref_model}')

        if 'default' in field_def:
            default_val = self._format_default(field_def['default'])
            if not is_required:
                field_type = f'Optional[{field_type}]'
            field_attrs.append(f'default={default_val}')
        elif 'x-default-expression' in field_def:
            expr = field_def['x-default-expression']
            if 'Date.now' in expr:
                # Handle Date.now() - can be converted to Python
                field_attrs.append('default_factory=lambda: datetime.now(timezone.utc)')
                self.imported_types.add('datetime')
                self.imported_types.add('timezone')
            else:
                # For other expressions (like SystemRoles.USER, enums, constants)
                # Try to generate a reasonable placeholder or keep as required field

                # Strategy 1: If it looks like an enum/constant (has dots), suggest a placeholder
                if '.' in expr:
                    # Extract the last part as hint: SystemRoles.USER -> USER
                    parts = expr.split('.')
                    hint = parts[-1] if len(parts) > 1 else 'unknown'

                    # Generate a placeholder string default
                    field_attrs.append(f'default="{hint}"')
                    comments.append(f'TODO: Verify default value. Original: {expr}')
                else:
                    # Strategy 2: For simple expressions, mark as required but add clear note
                    if not is_required:
                        field_type = f'Optional[{field_type}]'
                        field_attrs.append('default=None')
                    else:
                        field_attrs.append('...')
                    comments.append(f'DB default: {expr}')
        else:
            if not is_required:
                field_type = f'Optional[{field_type}]'
                field_attrs.append('default=None')
            else:
                field_attrs.append('...')

        if field_def.get('type') == 'string':
            if 'minLength' in field_def:
                field_attrs.append(f'min_length={field_def["minLength"]}')
            if 'maxLength' in field_def:
                field_attrs.append(f'max_length={field_def["maxLength"]}')
            if 'pattern' in field_def and field_type != 'PydanticObjectId' and not field_type.startswith('Link'):
                pattern = field_def['pattern'].replace('\\', '\\\\')
                field_attrs.append(f'pattern=r"{pattern}"')

        if field_attrs:
            field_call = f'Field({", ".join(field_attrs)})'
        else:
            field_call = 'Field(...)'

        result = f'    {field_name}: {field_type} = {field_call}'
        if comments:
            result += f'  # {", ".join(comments)}'

        return result

    def _get_python_type(self, field_def: Dict[str, Any]) -> str:
        """Convert JSON Schema type to Python type"""
        json_type = field_def.get('type')

        if field_def.get('pattern') == '^[0-9a-fA-F]{24}$':
            self.imported_types.add('PydanticObjectId')
            return 'PydanticObjectId'

        if json_type == 'string' and field_def.get('format') == 'date-time':
            self.imported_types.add('datetime')
            return 'datetime'

        if json_type == 'array':
            self.imported_types.add('List')
            items = field_def.get('items', {})
            if items:
                item_type = self._get_python_type(items)
                return f'List[{item_type}]'
            else:
                return 'List[Any]'

        if json_type == 'object' or field_def.get('x-mixed'):
            self.imported_types.add('Dict')
            return 'Dict[str, Any]'

        if 'additionalProperties' in field_def:
            self.imported_types.add('Dict')
            return 'Dict[str, Any]'

        python_type = self.TYPE_MAPPING.get(json_type, 'Any')

        if python_type in ('List', 'Dict'):
            self.imported_types.add(python_type)

        return python_type

    def _format_default(self, value: Any) -> str:
        """Format default value for Python code"""
        if value is None:
            return 'None'
        elif isinstance(value, bool):
            return 'True' if value else 'False'
        elif isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, list):
            return '[]'
        elif isinstance(value, dict):
            return '{}'
        else:
            return repr(value)

    def _generate_index(self, index_def: Dict[str, Any]) -> str:
        """Generate index definition for Settings.indexes"""
        fields = index_def.get('fields', {})

        field_list = []
        for field_name, direction in fields.items():
            field_list.append(f'("{field_name}", {direction})')

        if not field_list:
            return ''

        index_str = f'[{", ".join(field_list)}]'

        options = []
        if index_def.get('unique'):
            options.append('"unique": True')
        if index_def.get('sparse'):
            options.append('"sparse": True')
        if 'expireAfterSeconds' in index_def:
            options.append(f'"expireAfterSeconds": {index_def["expireAfterSeconds"]}')

        if options:
            index_str = f'([{", ".join(field_list)}], {{{", ".join(options)}}})'

        return index_str

    def _generate_imports(self, has_timestamps: bool) -> str:
        """Generate import statements based on used types"""
        imports = []

        datetime_imports = []
        if 'datetime' in self.imported_types:
            datetime_imports.append('datetime')
        if 'timezone' in self.imported_types:
            datetime_imports.append('timezone')

        if datetime_imports:
            imports.append(f'from datetime import {", ".join(datetime_imports)}')

        typing_imports = []
        if 'List' in self.imported_types:
            typing_imports.append('List')
        if 'Dict' in self.imported_types:
            typing_imports.append('Dict')
        typing_imports.append('Optional')
        typing_imports.append('Any')

        if typing_imports:
            imports.append(f'from typing import {", ".join(sorted(typing_imports))}')

        # Field is from pydantic, not beanie
        imports.append('from pydantic import Field')

        beanie_imports = ['Document']
        if 'PydanticObjectId' in self.imported_types:
            beanie_imports.append('PydanticObjectId')
        if 'Link' in self.imported_types:
            beanie_imports.append('Link')

        imports.append(f'from beanie import {", ".join(beanie_imports)}')

        return '\n'.join(imports)

    def save_model(self, model_code: str, filename: str) -> Path:
        """Save generated model to file in _generated directory"""
        module_name = Path(filename).stem
        py_file = self.generated_dir / f'{module_name}.py'

        with open(py_file, 'w', encoding='utf-8') as f:
            f.write(model_code)

        return py_file

    def generate_init_file(self, model_names: List[str]):
        """Generate __init__.py files - one in _generated and one in parent"""
        # Generate _generated/__init__.py
        generated_init = self.generated_dir / '__init__.py'
        lines = ['"""']
        lines.append('Auto-generated Beanie ODM Models')
        lines.append('')
        lines.append('⚠️  DO NOT EDIT - This directory is auto-generated')
        lines.append(f'Generated at: {datetime.now(timezone.utc).isoformat()}')
        lines.append('"""')
        lines.append('')

        for model_name in model_names:
            module = Path(model_name).stem
            class_name = ''.join(word.capitalize() for word in module.replace('_', ' ').split())
            if not class_name:
                class_name = 'Document'
            lines.append(f'from .{module} import {class_name}')

        lines.append('')
        lines.append('__all__ = [')
        for model_name in model_names:
            module = Path(model_name).stem
            class_name = ''.join(word.capitalize() for word in module.replace('_', ' ').split())
            if not class_name:
                class_name = 'Document'
            lines.append(f'    "{class_name}",')
        lines.append(']')
        lines.append('')

        with open(generated_init, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        # Generate parent __init__.py that exports from _generated
        parent_init = self.output_dir / '__init__.py'
        parent_lines = ['"""']
        parent_lines.append('Beanie ODM Models')
        parent_lines.append('')
        parent_lines.append('Exports auto-generated models from _generated/')
        parent_lines.append('"""')
        parent_lines.append('')
        parent_lines.append('from ._generated import (')
        
        for model_name in model_names:
            module = Path(model_name).stem
            class_name = ''.join(word.capitalize() for word in module.replace('_', ' ').split())
            if not class_name:
                class_name = 'Document'
            parent_lines.append(f'    {class_name},')
        
        parent_lines.append(')')
        parent_lines.append('')
        parent_lines.append('__all__ = [')
        for model_name in model_names:
            module = Path(model_name).stem
            class_name = ''.join(word.capitalize() for word in module.replace('_', ' ').split())
            if not class_name:
                class_name = 'Document'
            parent_lines.append(f'    "{class_name}",')
        parent_lines.append(']')
        parent_lines.append('')

        with open(parent_init, 'w', encoding='utf-8') as f:
            f.write('\n'.join(parent_lines))

        return generated_init

    def generate_init_file(self, models_info: List[tuple[str, str]]):
        """Generate __init__.py in _generated directory only
        
        Args:
            models_info: List of (filename, class_name) tuples
        """
        # Generate _generated/__init__.py
        generated_init = self.generated_dir / '__init__.py'
        lines = ['"""']
        lines.append('Auto-generated Beanie ODM Models')
        lines.append('')
        lines.append('⚠️  DO NOT EDIT - This directory is auto-generated')
        lines.append(f'Generated at: {datetime.now(timezone.utc).isoformat()}')
        lines.append('"""')
        lines.append('')

        for filename, class_name in models_info:
            module = Path(filename).stem
            lines.append(f'from .{module} import {class_name}')

        lines.append('')
        lines.append('__all__ = [')
        for filename, class_name in models_info:
            lines.append(f'    "{class_name}",')
        lines.append(']')
        lines.append('')

        with open(generated_init, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return generated_init

    def generate_readme(self, version: str, files: List[str], repo: str):
        """Generate README.md in _generated directory with generation instructions"""
        readme_file = self.generated_dir / 'README.md'
        
        lines = ['# Auto-Generated Models']
        lines.append('')
        lines.append('⚠️  **DO NOT EDIT FILES IN THIS DIRECTORY**')
        lines.append('')
        lines.append('This directory contains auto-generated Beanie ODM models from JSON schemas.')
        lines.append('')
        lines.append('## Generation Info')
        lines.append('')
        lines.append(f'- **Repository**: {repo}')
        lines.append(f'- **Version**: {version}')
        lines.append(f'- **Generated at**: {datetime.now(timezone.utc).isoformat()}')
        lines.append(f'- **Files**: {len(files)}')
        lines.append('')
        lines.append('## Regenerate Models')
        lines.append('')
        lines.append('To regenerate these models, run:')
        lines.append('')
        lines.append('```bash')
        lines.append(f'uv run import-schemas --tag {version} \\')
        lines.append(f'  --files {" ".join(files)} \\')
        lines.append('  --output-dir ./models \\')
        lines.append('  --token $(gh auth token)')
        lines.append('```')
        lines.append('')
        lines.append('## Files Generated')
        lines.append('')
        for f in files:
            module = Path(f).stem
            lines.append(f'- `{module}.py`')
        lines.append('')
        
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return readme_file

    def save_schema_version(self, version: str):
        """Save schema version to .schema-version file"""
        version_file = self.generated_dir / '.schema-version'
        
        with open(version_file, 'w', encoding='utf-8') as f:
            f.write(f'{version}\n')
        
        return version_file


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert JSON schemas to Beanie ODM models (supports local and remote modes)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Local mode - convert from local JSON files
  python import-schemas.py --mode local --input-dir ./dist/json-schemas --files user.json token.json --output-dir ./models

  # Remote mode - download from GitHub Release
  python import-schemas.py --mode remote --tag asc0.4.0 --files user.json token.json --output-dir ./models --token ghp_xxxxx

  # Remote mode (default) - public repository
  python import-schemas.py --tag asc0.4.0 --files user.json --output-dir ./models

GitHub Release URL format:
  https://github.com/{repo}/releases/download/{tag}/{filename}
        """
    )

    # Mode selection
    parser.add_argument(
        '--mode',
        choices=['local', 'remote'],
        default='remote',
        help='Mode: local (read from local directory) or remote (download from GitHub). Default: remote'
    )

    # Common arguments
    parser.add_argument(
        '--files',
        nargs='+',
        required=True,
        help='JSON schema filenames to convert (e.g., user.json token.json)'
    )
    parser.add_argument(
        '--output-dir',
        required=True,
        help='Output directory for generated Python models'
    )

    # Local mode arguments
    parser.add_argument(
        '--input-dir',
        help='[Local mode] Input directory containing JSON schema files (required for --mode local)'
    )

    # Remote mode arguments
    parser.add_argument(
        '--tag',
        help='[Remote mode] GitHub Release tag/version (e.g., asc0.4.0) (required for --mode remote)'
    )
    parser.add_argument(
        '--repo',
        default='ascending-llc/jarvis-api',
        help='[Remote mode] GitHub repository (default: ascending-llc/jarvis-api)'
    )
    parser.add_argument(
        '--token',
        help='[Remote mode] GitHub Personal Access Token (for private repos). Can also use GITHUB_TOKEN env var'
    )

    args = parser.parse_args()

    # Validate mode-specific required arguments
    if args.mode == 'local':
        if not args.input_dir:
            parser.error("--input-dir is required when --mode is 'local'")
    elif args.mode == 'remote':
        if not args.tag:
            parser.error("--tag is required when --mode is 'remote'")

    # Print mode information
    print("=" * 70)
    print("JSON Schema to Beanie ODM Model Converter")
    print("=" * 70)
    print(f"Mode: {args.mode.upper()}")

    generator = BeanieModelGenerator(
        output_dir=args.output_dir,
        github_repo=args.repo,
        github_token=args.token
    )

    generated_files = []
    failed_files = []
    models_info = []  # List of (filename, class_name) tuples

    if args.mode == 'local':
        print(f"Input directory: {args.input_dir}")
        print(f"Output directory: {args.output_dir}")
        print(f"Files to convert: {len(args.files)}\n")

        for filename in args.files:
            try:
                print(f"Processing: {filename}")
                schema = generator.load_local_schema(args.input_dir, filename)
                model_code, class_name = generator.generate_model(schema)
                py_file = generator.save_model(model_code, filename)
                generated_files.append(py_file)
                models_info.append((filename, class_name))
                print(f"  Generated: {py_file.name} ({class_name})")
            except Exception as e:
                print(f"  Error: {e}")
                failed_files.append((filename, str(e)))

    else:  # remote mode
        print(f"GitHub repository: {args.repo}")
        print(f"Release tag: {args.tag}")
        print(f"Output directory: {args.output_dir}")
        print(f"Files to download: {len(args.files)}\n")

        for filename in args.files:
            try:
                print(f"Downloading: {filename}")
                schema = generator.download_schema(args.tag, filename)
                model_code, class_name = generator.generate_model(schema)
                py_file = generator.save_model(model_code, filename)
                generated_files.append(py_file)
                models_info.append((filename, class_name))
                print(f"  Generated: {py_file.name} ({class_name})")
            except Exception as e:
                print(f"  Error: {e}")
                failed_files.append((filename, str(e)))

    print("\n" + "=" * 70)
    if generated_files:
        generator.generate_init_file(models_info)
        
        # Generate README and version file for remote mode
        if args.mode == 'remote':
            generator.generate_readme(args.tag, args.files, args.repo)
            generator.save_schema_version(args.tag)
            print(f"Successfully generated {len(generated_files)} model(s) in _generated/")
            print(f"Schema version: {args.tag}")
        else:
            print(f"Successfully generated {len(generated_files)} model(s) in _generated/")
        
        if failed_files:
            print(f"Failed: {len(failed_files)} file(s)")
            for filename, error in failed_files:
                print(f"  - {filename}: {error}")
    else:
        print("No files were generated")
        if failed_files:
            print(f"Failed: {len(failed_files)} file(s)")
            for filename, error in failed_files:
                print(f"  - {filename}: {error}")
    print("=" * 70)

    return 1 if failed_files else 0


if __name__ == '__main__':
    sys.exit(main())