"""Setup script for AI Trading System."""
import subprocess
import sys
import os
from pathlib import Path


def run_command(command, description):
    """Run a shell command and handle errors."""
    print(f"\n{'=' * 60}")
    print(f"{description}")
    print(f"{'=' * 60}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed")
        print(f"Error: {e.stderr}")
        return False


def main():
    """Run setup steps."""
    print("\n" + "=" * 60)
    print("AI TRADING SYSTEM - SETUP")
    print("=" * 60)
    
    # Check Python version
    if sys.version_info < (3, 10):
        print("✗ Python 3.10 or higher is required")
        sys.exit(1)
    
    print(f"✓ Python version: {sys.version}")
    
    # Create logs directory
    logs_dir = Path("logs")
    if not logs_dir.exists():
        logs_dir.mkdir()
        print("✓ Created logs directory")
    
    # Install dependencies
    if not run_command(
        f"{sys.executable} -m pip install -r requirements.txt",
        "Installing dependencies"
    ):
        print("\n⚠ Failed to install some dependencies")
        print("You may need to install them manually")
    
    # Create .env from template
    env_file = Path(".env")
    env_template = Path("env.template")
    
    if not env_file.exists() and env_template.exists():
        with open(env_template) as f:
            content = f.read()
        with open(env_file, 'w') as f:
            f.write(content)
        print("✓ Created .env file from template")
        print("  ⚠ Please update .env with your API credentials")
    
    # Initialize database
    print("\n" + "=" * 60)
    print("Initializing database")
    print("=" * 60)
    
    try:
        from backend.app.database import init_db
        init_db()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
    
    # Final instructions
    print("\n" + "=" * 60)
    print("SETUP COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Update .env file with your API credentials:")
    print("     - UPSTOX_API_KEY")
    print("     - UPSTOX_API_SECRET")
    print("     - OPENAI_API_KEY")
    print("\n  2. Run demo with mock data:")
    print("     python scripts/demo.py")
    print("\n  3. Start the server:")
    print("     uvicorn backend.app.main:app --reload")
    print("\n  4. Open http://localhost:8000 in your browser")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

