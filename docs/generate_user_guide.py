"""Render the Portuguese Markdown guide as a printable PDF."""

from pathlib import Path
import re

from fpdf import FPDF


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "GUIA_DE_USO.md"
OUTPUT = ROOT / "Guia_Dive_3D_Gen.pdf"
FONT_DIR = Path("C:/Windows/Fonts")


class GuidePDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(12, 68, 116)
        self.rect(0, 0, self.w, 10, style="F")
        self.set_font("Arial", "B", 8)
        self.set_text_color(255, 255, 255)
        self.set_xy(15, 2.8)
        self.cell(0, 4, "DIVE 3D GEN | GUIA DE USO")
        self.set_text_color(20, 25, 30)
        self.ln(10)

    def footer(self):
        self.set_y(-13)
        self.set_draw_color(190, 198, 205)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.set_font("Arial", size=8)
        self.set_text_color(100, 110, 120)
        self.cell(0, 7, f"Dive Smart Factory | Pagina {self.page_no()}", align="C")
        self.set_text_color(20, 25, 30)

    def add_title(self, text):
        self.set_y(42)
        self.set_x(self.l_margin)
        self.set_font("Arial", "B", 26)
        self.set_text_color(12, 68, 116)
        self.multi_cell(0, 11, text)
        self.set_x(self.l_margin)
        self.set_font("Arial", size=12)
        self.set_text_color(74, 84, 94)
        self.multi_cell(0, 7, "Guia de uso, distribuicao e auto-hospedagem")
        self.ln(8)
        self.set_draw_color(46, 144, 181)
        self.set_line_width(0.8)
        self.line(15, self.get_y(), self.w - 15, self.get_y())
        self.set_line_width(0.2)
        self.ln(10)
        self.set_text_color(20, 25, 30)

    def heading(self, text, level):
        if self.get_y() > self.h - 38:
            self.add_page()
        self.ln(3 if level == 2 else 1)
        self.set_font("Arial", "B", 15 if level == 2 else 12)
        self.set_text_color(12, 68, 116)
        self.set_x(self.l_margin)
        self.multi_cell(0, 7, text)
        self.set_text_color(20, 25, 30)
        self.ln(1)

    def paragraph(self, text):
        self.set_font("Arial", size=10.5)
        self.set_x(self.l_margin)
        self.multi_cell(0, 5.7, text)
        self.ln(1.2)

    def bullet(self, text, prefix="•"):
        self.set_font("Arial", size=10.5)
        x = self.l_margin
        y = self.get_y()
        self.set_x(x)
        self.cell(5, 5.7, prefix)
        self.set_xy(x + 5, y)
        self.multi_cell(self.w - self.r_margin - x - 5, 5.7, text)
        self.ln(0.5)

    def code(self, text):
        self.set_font("Consolas", size=8.5)
        self.set_fill_color(242, 245, 247)
        self.set_x(self.l_margin)
        self.multi_cell(0, 4.8, text or " ", fill=True)


def clean_text(text):
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", text)
    return text.replace("**", "").replace("`", "")


def render():
    pdf = GuidePDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(15, 15, 15)
    pdf.add_font("Arial", "", str(FONT_DIR / "arial.ttf"))
    pdf.add_font("Arial", "B", str(FONT_DIR / "arialbd.ttf"))
    pdf.add_font("Consolas", "", str(FONT_DIR / "consola.ttf"))
    pdf.set_title("Dive 3D Gen - Guia de Uso")
    pdf.set_author("Dive Smart Factory")
    pdf.add_page()

    in_code = False
    for raw_line in SOURCE.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            if not in_code:
                pdf.ln(2)
            continue
        if in_code:
            pdf.code(line)
            continue
        if not stripped:
            pdf.ln(1.5)
        elif stripped.startswith("# "):
            pdf.add_title(clean_text(stripped[2:]))
        elif stripped.startswith("## "):
            pdf.heading(clean_text(stripped[3:]), level=2)
        elif stripped.startswith("### "):
            pdf.heading(clean_text(stripped[4:]), level=3)
        elif stripped.startswith("- "):
            pdf.bullet(clean_text(stripped[2:]))
        elif re.match(r"^\d+\. ", stripped):
            number, text = stripped.split(". ", 1)
            pdf.bullet(clean_text(text), prefix=f"{number}.")
        else:
            pdf.paragraph(clean_text(stripped))

    pdf.output(str(OUTPUT))
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    render()
