"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
handle_query() calls run_agent() and maps session results to output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
from utils.style_profile import (
    clear_style_profile,
    load_style_profile,
    merge_style_profile,
    profile_summary,
)


def _format_listing(item: dict, session: dict) -> str:
    """Format listing, price check, and any search retry notes for the UI."""
    brand = item["brand"] if item.get("brand") else "Unbranded"
    colors = ", ".join(item["colors"])
    tags = ", ".join(item["style_tags"])
    lines = []

    adjustments = session.get("search_adjustments") or []
    if adjustments:
        lines.append(
            "ℹ️ No exact matches — retried with: "
            + "; ".join(adjustments)
            + "."
        )
        lines.append("")

    lines.extend([
        f"{item['title']}",
        f"${item['price']:.2f} on {item['platform'].capitalize()} · "
        f"{item['condition'].capitalize()} condition · Size {item['size']}",
        f"Brand: {brand} · Category: {item['category']}",
        f"Colors: {colors}",
        f"Style: {tags}",
        "",
        item["description"],
    ])

    if session.get("price_assessment"):
        lines.extend(["", "💰 Price check:", session["price_assessment"]])

    return "\n".join(lines)


def _format_outfit(session: dict) -> str:
    """Format outfit suggestion with trend and style-profile context."""
    lines = []

    profile = session.get("style_profile") or {}
    summary = profile_summary(profile)
    if summary:
        lines.append(f"👤 Using saved style profile: {summary}")
        lines.append("")

    trends = session.get("trends") or {}
    if trends.get("summary"):
        tag_text = ", ".join(trends.get("trending_tags") or [])
        lines.append(f"📈 Trends ({trends.get('source', 'mock data')}): {trends['summary']}")
        if tag_text:
            lines.append(f"   Hot tags: {tag_text}")
        lines.append("")

    lines.append(session.get("outfit_suggestion") or "")
    return "\n".join(lines).strip()


def handle_query(
    user_query: str,
    wardrobe_choice: str,
    style_preferences: str,
) -> tuple[str, str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Returns:
        (listing_text, outfit_suggestion, fit_card, profile_status)
    """
    if not user_query or not user_query.strip():
        saved = profile_summary(load_style_profile())
        status = f"Saved profile: {saved}" if saved else "No saved style profile yet."
        return "Please enter a search query.", "", "", status

    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    profile = load_style_profile()
    if style_preferences and style_preferences.strip():
        profile = merge_style_profile(style_preferences.strip())

    session = run_agent(
        user_query.strip(),
        wardrobe,
        style_profile=profile,
        save_style_from_query=True,
    )

    status = profile_summary(load_style_profile()) or "No saved style profile yet."
    status = f"Saved profile: {status}"

    if session["error"]:
        return session["error"], "", "", status

    return (
        _format_listing(session["selected_item"], session),
        _format_outfit(session),
        session["fit_card"] or "",
        status,
    )


def handle_clear_profile() -> str:
    clear_style_profile()
    return "Style profile cleared."


EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "vintage graphic tee size XXS under $30",  # triggers retry (stretch)
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "designer ballgown size XXS under $5",
]


def build_interface():
    saved = profile_summary(load_style_profile())
    profile_placeholder = saved or "e.g. vintage grunge, baggy fits, chunky sneakers"

    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        with gr.Row():
            style_input = gr.Textbox(
                label="Style preferences (saved across sessions)",
                placeholder=profile_placeholder,
                lines=1,
                scale=3,
            )
            profile_status = gr.Textbox(
                label="Profile status",
                value=f"Saved profile: {saved}" if saved else "No saved style profile yet.",
                interactive=False,
                scale=2,
            )

        with gr.Row():
            submit_btn = gr.Button("Find it", variant="primary")
            clear_btn = gr.Button("Clear saved profile")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=10,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=10,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=10,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe", ""] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice, style_input],
            label="Try these queries",
        )

        outputs = [listing_output, outfit_output, fitcard_output, profile_status]

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, style_input],
            outputs=outputs,
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, style_input],
            outputs=outputs,
        )
        clear_btn.click(fn=handle_clear_profile, outputs=profile_status)

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
