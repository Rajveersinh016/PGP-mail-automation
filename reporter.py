"""
reporter.py — PGP Container Glass Intelligence Platform
Generates a simplified, professional HTML email report and a single-sheet Excel report.
"""

import logging
import os
import tempfile
from datetime import datetime, timezone
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

log = logging.getLogger(__name__)

# Badges and theme styling
CATEGORY_BADGES = {
    "🏭 New Container Glass Factory":  {"emoji": "🏭", "bg": "#d4edda", "color": "#155724"},
    "🏗 Plant Expansion":              {"emoji": "🏗", "bg": "#cce5ff", "color": "#004085"},
    "🔥 Furnace Rebuild":              {"emoji": "🔥", "bg": "#f8d7da", "color": "#721c24"},
    "⚙ Machinery & Equipment":         {"emoji": "⚙", "bg": "#e2d9f3", "color": "#432874"},
    "🤝 Customer Partnership":        {"emoji": "🤝", "bg": "#fde8d0", "color": "#7d3a00"},
    "💰 Investment":                  {"emoji": "💰", "bg": "#d2f4ea", "color": "#0f5132"},
    "🌱 Sustainability":              {"emoji": "🌱", "bg": "#d1e7dd", "color": "#0f5132"},
    "🍾 Beverage Industry":           {"emoji": "🍾", "bg": "#e2d9f3", "color": "#432874"},
    "🌸 Luxury Packaging":            {"emoji": "🌸", "bg": "#fce7f3", "color": "#9d174d"},
    "📦 Container Glass Packaging":   {"emoji": "📦", "bg": "#dbeafe", "color": "#1e40af"},
    "🔬 Technology":                  {"emoji": "🔬", "bg": "#cff4fc", "color": "#055160"},
    "🌍 Industry Update":             {"emoji": "🌍", "bg": "#e2e3e5", "color": "#383d41"},
}


def _build_html_email(articles: list[dict], report_date: str) -> str:
    """Build a clean, simplified email body."""
    total = len(articles)
    cards_html = ""

    for a in articles:
        cat = a.get("category", "🌍 Industry Update")
        badge = CATEGORY_BADGES.get(cat, CATEGORY_BADGES["🌍 Industry Update"])
        
        company = a.get("company", "Unknown")
        country = a.get("country", "Unknown")
        summary = a.get("summary", a.get("title", ""))
        source = a.get("source", "")
        pub_date = a.get("published", "")[:10] if a.get("published") else ""
        url = a.get("url", "#")
        business_impact = a.get("business_impact", "")

        meta_html = ""
        if company != "Unknown":
            meta_html += f'<strong>Company:</strong> {company} &nbsp;|&nbsp; '
        if country != "Unknown":
            meta_html += f'<strong>Country:</strong> {country} &nbsp;|&nbsp; '
        if source:
            meta_html += f'<strong>Source:</strong> {source} &nbsp;|&nbsp; '
        if pub_date:
            meta_html += f'<strong>Date:</strong> {pub_date}'

        impact_html = f"""
        <p style="margin:8px 0 0 0; font-size:12px; color:#1e40af; line-height:1.5; font-family:Arial,sans-serif;">
          <strong>💼 Business Impact:</strong> {business_impact}
        </p>""" if business_impact else ""

        cards_html += f"""
        <tr>
          <td style="padding:16px 0; border-bottom:1px solid #e2e8f0;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td>
                  <!-- Category Badge -->
                  <span style="display:inline-block; background:{badge['bg']}; color:{badge['color']};
                               font-size:10px; font-weight:700; padding:3px 8px; border-radius:12px;
                               font-family:Arial,sans-serif; margin-bottom:6px;">
                    {badge['emoji']} {cat.upper()}
                  </span>
                  <!-- Title -->
                  <h3 style="margin:0 0 4px 0; font-size:15px; font-weight:700; color:#0f172a; line-height:1.4; font-family:Arial,sans-serif;">
                    <a href="{url}" style="color:#0f172a; text-decoration:none;" target="_blank">{a.get('title', '')}</a>
                  </h3>
                  <!-- Meta row -->
                  <p style="margin:0 0 8px 0; font-size:11.5px; color:#64748b; font-family:Arial,sans-serif;">
                    {meta_html}
                  </p>
                  <!-- Summary block -->
                  <div style="background:#f8fafc; padding:10px 14px; border-left:3px solid #092f20; border-radius:0 6px 6px 0; margin-bottom:8px;">
                    <p style="margin:0; font-size:13px; color:#334155; line-height:1.5; font-family:Arial,sans-serif;">
                      {summary}
                    </p>
                    {impact_html}
                  </div>
                  <!-- Link -->
                  <a href="{url}" target="_blank" style="display:inline-block; font-size:11.5px; font-weight:600; color:#092f20; text-decoration:none; font-family:Arial,sans-serif;">
                    Read Article →
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Container Glass Intelligence Report</title>
</head>
<body style="margin:0; padding:0; background-color:#f1f5f9; font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f1f5f9; padding:20px 0;">
    <tr>
      <td align="center">
        <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px; background:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.1);">
          <!-- Header -->
          <tr>
            <td style="background:#092f20; padding:24px 30px; border-bottom:3px solid #10b981;">
              <p style="margin:0 0 2px 0; font-size:10px; font-weight:600; color:#34d399; letter-spacing:1.5px; text-transform:uppercase;">
                CONTAINER GLASS INTELLIGENCE PLATFORM
              </p>
              <h1 style="margin:0; font-size:22px; font-weight:700; color:#ffffff; font-family:Arial,sans-serif;">
                Daily Market Report
              </h1>
              <p style="margin:4px 0 0 0; font-size:12px; color:#93c5fd; font-family:Arial,sans-serif;">
                {report_date} &nbsp;·&nbsp; {total} Curated Updates
              </p>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:10px 30px 30px 30px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                {cards_html}
              </table>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background:#f8fafc; border-top:1px solid #e2e8f0; padding:16px 30px; font-size:11px; color:#64748b; line-height:1.5;">
              This curated report is compiled daily for internal strategic intelligence.<br>
              Excel attachment containing final curated articles metadata is attached.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    return html


def _build_excel(articles: list[dict]) -> str:
    """Build a single-sheet Excel workbook and save to temp file. Returns file path."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Curated Articles"
    ws.row_dimensions[1].height = 25

    headers = ["Company", "Country", "Category", "Summary", "Source", "Published Date", "URL"]
    ws.append(headers)

    # Style Header Row
    fill = PatternFill(start_color="092F20", end_color="092F20", fill_type="solid")
    font = Font(bold=True, color="FFFFFF", size=10, name="Calibri")
    alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    border = Border(bottom=Side(style="medium", color="10B981"))

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = fill
        cell.font = font
        cell.alignment = alignment
        cell.border = border

    alt_fill = PatternFill(start_color="F4Fbf7", end_color="F4Fbf7", fill_type="solid")
    normal_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

    for i, a in enumerate(articles, 1):
        row_fill = alt_fill if i % 2 == 0 else normal_fill
        pub_date = a.get("published", "")[:10] if a.get("published") else ""
        row = [
            a.get("company", "Unknown"),
            a.get("country", "Unknown"),
            a.get("category", "🌍 Industry Update"),
            a.get("summary", ""),
            a.get("source", ""),
            pub_date,
            a.get("url", ""),
        ]
        ws.append(row)
        
        # Apply Row styling
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=i + 1, column=col_idx)
            cell.fill = row_fill
            cell.font = Font(name="Calibri", size=9)
            cell.alignment = Alignment(vertical="top", wrap_text=(col_idx in (4, 7)))

    # Set column widths
    widths = [18, 14, 24, 55, 18, 12, 25]
    for idx, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = w

    # Save to temp file
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"container_glass_report_{date_str}.xlsx"
    excel_path = os.path.join(tempfile.gettempdir(), filename)
    wb.save(excel_path)
    return excel_path


def generate_report(articles: list[dict]) -> tuple[str, str]:
    """Public interface: returns HTML email body and Excel file path."""
    report_date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    
    # Sort by Company name for structured display
    articles = sorted(articles, key=lambda x: x.get("company", "Unknown").lower())

    html_body = _build_html_email(articles, report_date)
    excel_path = _build_excel(articles)

    return html_body, excel_path
