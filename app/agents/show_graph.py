import argparse
import importlib
import importlib.util
from pathlib import Path
from typing import Any
import webbrowser


def resolve_target(target: str) -> Any:
    """
    Resolve an import target in the form: module.submodule:object_name
    Example: app.agents.input_controler:controller_app
    """
    if ":" not in target:
        raise ValueError("Target must be in format 'module.path:object_name'")

    module_name, object_name = target.split(":", 1)

    # Support loading from Python file path as module target.
    # Example: app/agents/input_controler.py:controller_app
    if module_name.endswith(".py") or "/" in module_name or "\\" in module_name:
        file_path = Path(module_name)
        if not file_path.exists():
            raise FileNotFoundError(f"Python file not found: {file_path}")

        spec = importlib.util.spec_from_file_location("graph_target_module", file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from file: {file_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_name)

    if not hasattr(module, object_name):
        raise AttributeError(f"'{module_name}' has no attribute '{object_name}'")

    return getattr(module, object_name)


def extract_mermaid(graph_obj: Any) -> str:
    """
    Extract Mermaid diagram text from a LangGraph object.
    Supports compiled graphs and graph builders that expose draw/get_graph methods.
    """
    # Common case for compiled LangGraph app
    if hasattr(graph_obj, "get_graph"):
        drawable = graph_obj.get_graph()
        if hasattr(drawable, "draw_mermaid"):
            return drawable.draw_mermaid()

    # Some objects may directly expose draw_mermaid
    if hasattr(graph_obj, "draw_mermaid"):
        return graph_obj.draw_mermaid()

    raise TypeError(
        "Could not extract Mermaid from object. Expected a LangGraph compiled app "
        "(with get_graph().draw_mermaid()) or a drawable graph object."
    )


def save_mermaid(mermaid: str, out_path: str) -> Path:
        """
        Save Mermaid text to a file.
        """
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(mermaid, encoding="utf-8")
        return path


def render_mermaid_html(mermaid: str) -> str:
        """
        Build an HTML page that renders Mermaid markup in browser.
        """
        return f"""<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Graph Viewer</title>
    <script type=\"module\">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 16px; }}
        .mermaid {{ overflow: auto; border: 1px solid #ddd; padding: 12px; border-radius: 8px; }}
    </style>
</head>
<body>
    <h2>Graph Diagram</h2>
    <div class=\"mermaid\">{mermaid}</div>
</body>
</html>
"""


def plot_graph(graph_obj: Any, out_html: str = "graph.html", open_browser: bool = False) -> Path:
        """
        Plot a LangGraph object by generating an HTML Mermaid visualization.

        Args:
                graph_obj: Compiled LangGraph app or drawable graph object.
                out_html: Output HTML file path.
                open_browser: Whether to open the output HTML in default browser.

        Returns:
                Path to generated HTML file.
        """
        mermaid = extract_mermaid(graph_obj)
        html = render_mermaid_html(mermaid)
        output_path = Path(out_html)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")

        if open_browser:
                webbrowser.open(output_path.resolve().as_uri())

        return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load a graph object by import path and show its Mermaid diagram."
    )
    parser.add_argument(
        "target",
        help=(
            "Target in format module.path:object_name or file/path.py:object_name "
            "(e.g. app.agents.input_controler:controller_app or "
            "app/agents/input_controler.py:controller_app)"
        ),
        default="app.agents.input_controler:controller_app"
    )
    parser.add_argument(
        "--out",
        help="Optional output file path for Mermaid text (e.g. graph.mmd)",
        default=None,
    )
    parser.add_argument(
        "--html",
        help="Optional output HTML file path for rendered graph (e.g. graph.html)",
        default=None,
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open generated HTML graph in browser (use with --html)",
    )
    args = parser.parse_args()

    graph_obj = resolve_target(args.target)
    
    # If the target is a callable (like a function that builds a graph), call it
    if callable(graph_obj):
        graph_obj = graph_obj()
    
    mermaid = extract_mermaid(graph_obj)

    print("\n=== Mermaid Diagram ===\n")
    print(mermaid)

    if args.out:
        out_path = save_mermaid(mermaid, args.out)
        print(f"\nSaved Mermaid diagram to: {out_path}")

    if args.html:
        html_path = plot_graph(graph_obj, out_html=args.html, open_browser=args.open)
        print(f"Saved rendered HTML graph to: {html_path}")


if __name__ == "__main__":
    main()
