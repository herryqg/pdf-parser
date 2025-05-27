import pikepdf

pdf = pikepdf.open("output.pdf")
for page in pdf.pages:
    font_dict = page["/Resources"]["/Font"]
    for font_name, font in font_dict.items():
        if "/ToUnicode" in font:
            cmap = font["/ToUnicode"].read_bytes().decode("utf-8", errors="ignore")
            print(f"=== CMap for {font_name} ===")
            print(cmap)