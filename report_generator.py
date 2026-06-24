from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, PageBreak, TableStyle
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch, cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageTemplate, Frame, NextPageTemplate
from reportlab.lib.units import inch
import pandas as pd
import tempfile
import os
import io
from io import BytesIO
from datetime import datetime

def _register_thai_fonts():
    """Register Thai fonts for PDF generation"""
    try:
        # Try to find and register Thai fonts from assets/fonts
        base_dir = os.path.dirname(__file__)
        font_paths = [
            os.path.join(base_dir, "assets", "fonts", "THSarabunNew.ttf"),
            os.path.join(base_dir, "assets", "fonts", "THSarabunNew Bold.ttf"),
        ]
        
        registered_fonts = {}
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font_name = os.path.splitext(os.path.basename(font_path))[0]
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    registered_fonts[font_name] = font_path
                    print(f"Successfully registered font: {font_name}")
                except Exception as e:
                    print(f"Failed to register font {font_path}: {e}")
                    continue
        
        if registered_fonts:
            return registered_fonts
        else:
            print("No Thai fonts found, using default")
            return {"default": "Helvetica"}
        
    except Exception as e:
        print(f"Font registration error: {e}")
        return {"default": "Helvetica"}

def _create_header_footer(canvas, doc):
    """Create clean header and footer with page numbers"""
    canvas.saveState()
    
    # Clean header with minimal design
    canvas.setFont("THSarabunNew", 10)
    canvas.setStrokeColor(colors.grey)
    canvas.setFillColor(colors.grey)
    
    # Header line
    canvas.line(2*cm, A4[1]-1.5*cm, A4[0]-2*cm, A4[1]-1.5*cm)
    
    # Footer with page number and date
    canvas.setFont("THSarabunNew", 9)
    page_num = canvas.getPageNumber()
    canvas.drawString(2*cm, 1.5*cm, f"หน้า {page_num}")
    
    # Current date
    current_date = datetime.now().strftime("%d/%m/%Y %H:%M")
    canvas.drawRightString(A4[0]-2*cm, 1.5*cm, current_date)
    
    canvas.restoreState()

def _format_number(value):
    """Format number with thousand separators and decimal places"""
    try:
        if pd.isna(value):
            return "N/A"
        if isinstance(value, (int, float)):
            if value == int(value):
                return f"{int(value):,}"
            else:
                return f"{value:,.3f}"
        return str(value)
    except Exception:
        return str(value)

def _dedupe_columns(columns):
    """Remove duplicate columns while preserving order"""
    seen = set()
    deduped = []
    for col in columns:
        if col not in seen:
            seen.add(col)
            deduped.append(col)
    return deduped

def _create_kpi_cards(df, columns_to_analyze):
    """Create KPI cards showing key statistics"""
    if not columns_to_analyze:
        return None
    
    # Calculate KPIs for the first few columns
    kpi_data = []
    for i, col in enumerate(columns_to_analyze[:4]):  # Limit to 4 columns for KPI cards
        try:
            col_data = df[col].dropna()
            if len(col_data) > 0:
                mean_val = col_data.mean()
                std_val = col_data.std()
                min_val = col_data.min()
                max_val = col_data.max()
                
                kpi_data.append([
                    col,
                    f"{len(col_data):,}",
                    f"{mean_val:.2f}",
                    f"{std_val:.2f}",
                    f"{min_val:.2f}",
                    f"{max_val:.2f}"
                ])
        except Exception:
            continue
    
    if not kpi_data:
        return None
    
    # Create KPI table
    headers = ["คอลัมน์", "จำนวนข้อมูล", "ค่าเฉลี่ย", "ส่วนเบี่ยงเบน", "ค่าต่ำสุด", "ค่าสูงสุด"]
    table_data = [headers] + kpi_data
    
    return table_data

def export_report(fig, df: pd.DataFrame, meta: dict, save_path: str, options: dict = None):
    """
    Export a comprehensive report to PDF with Academic-Clean template
    
    Args:
        fig: matplotlib figure object
        df: pandas DataFrame with the data
        meta: dictionary containing metadata (filename, columns used, etc.)
        save_path: path where to save the PDF report
        options: dictionary with options for report content
    """
    # Set default options if not provided
    if options is None:
        options = {
            "title": "รายงานการวิเคราะห์ข้อมูล SciPlotter",
            "include_meta": True,
            "include_stats": True,
            "include_fig": True,
            "columns": list(df.columns) if df is not None else []
        }
    
    # Dedupe columns while preserving order
    if options["columns"]:
        options["columns"] = _dedupe_columns(options["columns"])
    
    # Set default title if empty
    if not options["title"].strip():
        options["title"] = "รายงานการวิเคราะห์ข้อมูล SciPlotter"
    
    try:
        # Register Thai fonts
        fonts = _register_thai_fonts()
        thai_font = list(fonts.keys())[0] if fonts else "Helvetica"
        thai_bold_font = "THSarabunNew Bold" if "THSarabunNew Bold" in fonts else thai_font
        
        print(f"Using fonts: {fonts}")
        
        # Create document with portrait A4 for better academic layout
        doc = SimpleDocTemplate(save_path, pagesize=A4)
        
        # Create page template with header/footer
        frame = Frame(2*cm, 2*cm, A4[0]-4*cm, A4[1]-4*cm)
        page_template = PageTemplate(id='custom', frames=[frame], onPage=_create_header_footer)
        doc.addPageTemplates([page_template])
        
        story = []
        
        # Create custom styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontName=thai_bold_font,
            fontSize=20,
            spaceAfter=25,
            alignment=1,  # Center
            textColor=colors.darkblue
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=thai_bold_font,
            fontSize=14,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkblue
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName=thai_font,
            fontSize=11,
            spaceAfter=6
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontName=thai_font,
            fontSize=12,
            spaceAfter=15,
            textColor=colors.grey
        )

        # Hero Header Section
        story.append(Paragraph(options["title"], title_style))
        
        # Subtitle with timestamp
        timestamp = datetime.now().strftime("%d %B %Y เวลา %H:%M น.")
        story.append(Paragraph(f"สร้างเมื่อ: {timestamp}", subtitle_style))
        story.append(Spacer(1, 20))

        # Metadata section (only if include_meta is True)
        if options["include_meta"]:
            story.append(Paragraph("ข้อมูลไฟล์", heading_style))
            
            # Create metadata table
            meta_data = []
            filename = meta.get('filename', 'N/A')
            meta_data.append(["ชื่อไฟล์", filename])
            
            if 'columns_used' in meta and meta['columns_used']:
                columns_used = meta.get('columns_used', [])
                meta_data.append(["คอลัมน์ที่ใช้ในการพล็อต", ", ".join(columns_used)])
            
            meta_data.append(["จำนวนแถว", f"{len(df):,}"])
            meta_data.append(["จำนวนคอลัมน์", f"{len(df.columns):,}"])
            
            # Add dataset name if available
            if 'dataset_name' in meta:
                meta_data.append(["ชื่อชุดข้อมูล", meta['dataset_name']])
            
            # Create metadata table
            meta_table = Table(meta_data, colWidths=[3*cm, 12*cm])
            meta_table.setStyle([
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), thai_font),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightblue),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.darkblue),
                ('FONTNAME', (0, 0), (0, -1), thai_bold_font),
            ])
            
            story.append(meta_table)
            story.append(Spacer(1, 20))

        # KPI Cards Section (only if include_stats is True)
        if options["include_stats"]:
            story.append(Paragraph("สรุปสถิติหลัก", heading_style))
            
            try:
                # Use selected columns or all columns if none selected
                columns_to_analyze = options["columns"] if options["columns"] else list(df.columns)
                if not columns_to_analyze:
                    columns_to_analyze = list(df.columns)
                
                # Create KPI cards
                kpi_data = _create_kpi_cards(df, columns_to_analyze)
                if kpi_data:
                    kpi_table = Table(kpi_data, repeatRows=1)
                    kpi_table.setStyle([
                        # Header row styling
                        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), thai_bold_font),
                        ('FONTSIZE', (0, 0), (-1, 0), 11),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                        ('TOPPADDING', (0, 0), (-1, 0), 8),
                        
                        # Data rows styling with zebra pattern
                        ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Column names left-aligned
                        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),  # Numbers right-aligned
                        ('FONTNAME', (0, 1), (-1, -1), thai_font),
                        ('FONTSIZE', (0, 1), (-1, -1), 10),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                        
                        # Specific column styling
                        ('FONTNAME', (0, 1), (0, -1), thai_bold_font),  # Column names bold
                        ('BACKGROUND', (0, 1), (0, -1), colors.lightblue),  # Column names background
                    ])
                    
                    story.append(kpi_table)
                    story.append(Spacer(1, 20))
                
                # Detailed Statistics Table
                story.append(Paragraph("สถิติรายละเอียด", heading_style))
                
                # Filter DataFrame to selected columns
                df_stats = df[columns_to_analyze]
                stats = df_stats.describe().round(3)
                
                # Create detailed table data with formatted numbers
                table_data = [["คอลัมน์", "จำนวน", "ค่าเฉลี่ย", "ส่วนเบี่ยงเบน", "ค่าต่ำสุด", "25%", "50%", "75%", "ค่าสูงสุด"]]
                
                for col in stats.columns:
                    col_stats = stats[col]
                    row = [col] + [_format_number(col_stats.get(stat, 'N/A')) for stat in ['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max']]
                    table_data.append(row)
                
                # Create and style the detailed table
                detailed_table = Table(table_data, repeatRows=1)
                detailed_table.setStyle([
                    # Header row styling
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), thai_bold_font),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    
                    # Data rows styling with zebra pattern
                    ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Column names left-aligned
                    ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),  # Numbers right-aligned
                    ('FONTNAME', (0, 1), (-1, -1), thai_font),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                    
                    # Specific column styling
                    ('FONTNAME', (0, 1), (0, -1), thai_bold_font),  # Column names bold
                    ('BACKGROUND', (0, 1), (0, -1), colors.lightblue),  # Column names background
                ])
                
                story.append(detailed_table)
                story.append(Spacer(1, 25))
                
            except Exception as e:
                story.append(Paragraph(f"เกิดข้อผิดพลาดในการสร้างสถิติ: {str(e)}", normal_style))
                story.append(Spacer(1, 20))

        # Plot image (only if include_fig is True)
        if options["include_fig"]:
            story.append(Paragraph("กราฟที่สร้าง", heading_style))
            
            try:
                # Save figure to BytesIO instead of temporary file
                img_buffer = BytesIO()
                fig.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight', 
                           facecolor='white', edgecolor='none')
                img_buffer.seek(0)
                
                # Add image to report with full width and caption
                img = Image(img_buffer, width=15*cm, height=10*cm)
                story.append(img)
                
                # Add caption
                caption_style = ParagraphStyle(
                    'Caption',
                    parent=styles['Normal'],
                    fontName=thai_font,
                    fontSize=10,
                    spaceAfter=20,
                    alignment=1,  # Center
                    textColor=colors.grey
                )
                story.append(Paragraph("รูปที่ 1: กราฟแสดงผลการวิเคราะห์ข้อมูล", caption_style))
                
            except Exception as e:
                story.append(Paragraph(f"เกิดข้อผิดพลาดในการเพิ่มกราฟ: {str(e)}", normal_style))
                story.append(Spacer(1, 20))

        # Build the PDF
        doc.build(story)
        return True
        
    except Exception as e:
        print(f"Error generating report: {e}")
        return False
