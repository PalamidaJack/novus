"""CLI package for NOVUS."""

def main():
    """Lazy CLI entrypoint to avoid eager module side effects."""
    from novus.cli.main import main as _main

    return _main()

__all__ = ["main"]
