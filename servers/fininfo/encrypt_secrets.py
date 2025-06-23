#!/usr/bin/env python3
"""
Utility script to encrypt secrets files for the Financial Info MCP Server.

Usage:
    python encrypt_secrets.py [input_file] [output_file]

Examples:
    # Encrypt the default secrets file
    python encrypt_secrets.py

    # Encrypt a specific file
    python encrypt_secrets.py plain.yml encrypted.yml

    # Test decryption
    python encrypt_secrets.py --test encrypted.yml
"""

import os
import sys
import argparse
from secrets_manager import SecretsManager


def main():
    parser = argparse.ArgumentParser(description='Encrypt/decrypt secrets files')
    parser.add_argument('input_file', nargs='?', default='.keys.yml',
                       help='Input file path (default: .keys.yml)')
    parser.add_argument('output_file', nargs='?',
                       help='Output file path (default: input_file.encrypted)')
    parser.add_argument('--test', action='store_true',
                       help='Test decryption of an encrypted file')
    parser.add_argument('--decrypt', action='store_true',
                       help='Decrypt an encrypted file')
    
    args = parser.parse_args()
    
    # Check if SECRET_KEY is available
    if not os.environ.get("SECRET_KEY"):
        print("ERROR: SECRET_KEY environment variable is required for encryption/decryption")
        print("Please set SECRET_KEY in your environment or .env file")
        sys.exit(1)
    
    if args.test:
        print(f"Testing decryption of: {args.input_file}")
        try:
            # Try to load the encrypted file
            secrets_manager = SecretsManager(args.input_file)
            client_ids = secrets_manager.get_all_client_ids()
            print(f"✅ Successfully decrypted and loaded {len(client_ids)} client configurations")
            print(f"Client IDs: {client_ids}")
        except Exception as e:
            print(f"❌ Failed to decrypt file: {e}")
            sys.exit(1)
    
    elif args.decrypt:
        print(f"Decrypting: {args.input_file}")
        output_file = args.output_file or args.input_file.replace('.encrypted', '.decrypted')
        
        try:
            # Load encrypted file and save as plain text
            secrets_manager = SecretsManager(args.input_file)
            
            # Save as plain YAML
            import yaml
            with open(output_file, 'w') as f:
                yaml.dump(secrets_manager.secrets, f, default_flow_style=False)
            
            print(f"✅ Successfully decrypted to: {output_file}")
            
        except Exception as e:
            print(f"❌ Failed to decrypt file: {e}")
            sys.exit(1)
    
    else:
        # Encrypt mode
        print(f"Encrypting: {args.input_file}")
        
        if not os.path.exists(args.input_file):
            print(f"ERROR: Input file does not exist: {args.input_file}")
            sys.exit(1)
        
        # Initialize secrets manager and encrypt
        secrets_manager = SecretsManager()
        
        success = secrets_manager.encrypt_secrets_file(
            input_file=args.input_file,
            output_file=args.output_file
        )
        
        if success:
            output_file = args.output_file or (args.input_file + '.encrypted')
            print(f"✅ Successfully encrypted to: {output_file}")
            print("\nTo use the encrypted file:")
            print(f"1. Replace your plain text secrets file with the encrypted version")
            print(f"2. The secrets manager will automatically detect and decrypt it")
            print(f"3. Ensure SECRET_KEY environment variable is available")
        else:
            print("❌ Encryption failed")
            sys.exit(1)


if __name__ == "__main__":
    main()