from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, PageBreak
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
    """Create header and footer with page numbers"""
    canvas.saveState()
    
    # Header
    canvas.setFont("THSarabunNew", 12)
    canvas.drawString(2*cm, A4[1]-2*cm, "SciPlotter - Data Analysis Report")
    
    # Footer with page number
    canvas.setFont("THSarabunNew", 10)
    page_num = canvas.getPageNumber()
    canvas.drawString(2*cm, 1*cm, f"Page {page_num}")
    
    # Current date
    from datetime import datetime
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    canvas.drawRightString(A4[0]-2*cm, 1*cm, current_date)
    
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
    except:
        return str(value)

def export_report(fig, df: pd.DataFrame, meta: dict, save_path: str, options: dict = None):
    """
    Export a comprehensive report to PDF containing data analysis and plots
    
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
    try:
        # Register Thai fonts
        fonts = _register_thai_fonts()
        thai_font = list(fonts.keys())[0] if fonts else "Helvetica"
        thai_bold_font = "THSarabunNew Bold" if "THSarabunNew Bold" in fonts else thai_font
        
        print(f"Using fonts: {fonts}")
        
        # Create document with landscape A4
        doc = SimpleDocTemplate(save_path, pagesize=landscape(A4))
        
        # Create page template with header/footer
        frame = Frame(2*cm, 2*cm, landscape(A4)[0]-4*cm, landscape(A4)[1]-4*cm)
        page_template = PageTemplate(id='custom', frames=[frame], onPage=_create_header_footer)
        doc.addPageTemplates([page_template])
        
        story = []
        
        # Create custom styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontName=thai_bold_font,
            fontSize=18,
            spaceAfter=20,
            alignment=1  # Center
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=thai_bold_font,
            fontSize=14,
            spaceAfter=10,
            spaceBefore=15
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName=thai_font,
            fontSize=12,
            spaceAfter=5
        )

        # Title
        story.append(Paragraph(options["title"], title_style))
        story.append(Spacer(1, 20))

        # Metadata section (only if include_meta is True)
        if options["include_meta"]:
            story.append(Paragraph("ข้อมูลไฟล์", heading_style))
            
            filename = meta.get('filename', 'N/A')
            story.append(Paragraph(f"ชื่อไฟล์: {filename}", normal_style))
            
            if 'columns_used' in meta:
                columns_used = meta.get('columns_used', [])
                if columns_used:
                    story.append(Paragraph(f"คอลัมน์ที่ใช้ในการพล็อต: {', '.join(columns_used)}", normal_style))
            
            story.append(Spacer(1, 15))

            # Data overview
            story.append(Paragraph("ภาพรวมข้อมูล", heading_style))
            
            story.append(Paragraph(f"จำนวนแถว: {len(df):,}", normal_style))
            story.append(Paragraph(f"จำนวนคอลัมน์: {len(df.columns):,}", normal_style))
            story.append(Spacer(1, 15))

        # Statistics table (only if include_stats is True)
        if options["include_stats"]:
            story.append(Paragraph("สรุปสถิติ", heading_style))
            
            try:
                # Use selected columns or all columns if none selected
                columns_to_analyze = options["columns"] if options["columns"] else list(df.columns)
                if not columns_to_analyze:
                    columns_to_analyze = list(df.columns)
                
                # Filter DataFrame to selected columns
                df_stats = df[columns_to_analyze]
                stats = df_stats.describe().round(3)
                
                # Create table data with formatted numbers
                table_data = [["คอลัมน์", "จำนวน", "ค่าเฉลี่ย", "ส่วนเบี่ยงเบน", "ค่าต่ำสุด", "25%", "50%", "75%", "ค่าสูงสุด"]]
                
                for col in stats.columns:
                    col_stats = stats[col]
                    row = [col] + [_format_number(col_stats.get(stat, 'N/A')) for stat in ['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max']]
                    table_data.append(row)
                
                # Create and style the table
                table = Table(table_data, repeatRows=1)
                table.setStyle([
                    # Header row styling
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), thai_bold_font),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('TOPPADDING', (0, 0), (-1, 0), 8),
                    
                    # Data rows styling
                    ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
                    ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Column names left-aligned
                    ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),  # Numbers right-aligned
                    ('FONTNAME', (0, 1), (-1, -1), thai_font),
                    ('FONTSIZE', (0, 1), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                    
                    # Specific column styling
                    ('FONTNAME', (0, 1), (0, -1), thai_bold_font),  # Column names bold
                ])
                
                story.append(table)
                story.append(Spacer(1, 20))
                
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
                
                # Add image to report with appropriate size for landscape
                img = Image(img_buffer, width=10*inch, height=6*inch)
                story.append(img)
                
            except Exception as e:
                story.append(Paragraph(f"เกิดข้อผิดพลาดในการเพิ่มกราฟ: {str(e)}", normal_style))
                story.append(Spacer(1, 20))

        # Build the PDF
        doc.build(story)
        return True
        
    except Exception as e:
        print(f"Error generating report: {e}")
        return False
