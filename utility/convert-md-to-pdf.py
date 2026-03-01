from markdown_pdf import MarkdownPdf, Section

def md_to_pdf(input_file, output_file):
    # 1. Leggi il contenuto del file Markdown
    with open(input_file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # 2. Crea l'oggetto PDF
    # toc_level=2 genera automaticamente un sommario dai titoli # e ##
    pdf = MarkdownPdf(toc_level=2)

    # 3. Aggiungi il contenuto come una sezione
    pdf.add_section(Section(md_content))

    # 4. Salva il file PDF
    pdf.save(output_file)
    print(f"Successo! File salvato come: {output_file}")

# Esempio di utilizzo
if __name__ == "__main__":
    md_to_pdf("D:/tender/tenderwriter/repomix-output.md", "D:/tender/tenderwriter/repomix-output.pdf")
    

