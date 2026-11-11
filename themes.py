"""Declarative themes. Imported files contain colors only, never executable QSS/assets."""
import re
THEMES={
 'Cyber Neon':dict(background='#111827',panel='#25334b',text='#e5e7eb',accent='#22d3ee',border='#41516c'),
 'Cinema Black':dict(background='#141414',panel='#262626',text='#eeeeee',accent='#f6bd60',border='#555555'),
 'Light':dict(background='#f5f7fb',panel='#ffffff',text='#172033',accent='#0066bb',border='#9aa8bb'),
 'AMOLED':dict(background='#000000',panel='#101010',text='#ffffff',accent='#7dd3fc',border='#444444'),
 'High Contrast':dict(background='#000000',panel='#000000',text='#ffffff',accent='#ffff00',border='#ffffff'),
}
def validate_theme(data):
    if not isinstance(data,dict) or set(data)!=set(THEMES['Cyber Neon']):raise ValueError('Skin harus memuat tepat lima warna: background, panel, text, accent, border.')
    if any(not isinstance(v,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in data.values()):raise ValueError('Warna skin harus #RRGGBB.')
    return dict(data)
def stylesheet(data):
    c=validate_theme(data)
    return '''QMainWindow,QWidget{{background:{background};color:{text};}}
QPushButton,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QListWidget,QTableWidget{{background:{panel};color:{text};padding:6px;border:1px solid {border};border-radius:4px;}}
QPushButton:hover{{border:1px solid {accent};}} QPushButton:focus,QLineEdit:focus,QComboBox:focus{{border:2px solid {accent};}}
QPushButton:disabled{{color:{border};}} QMenu::item:selected,QListWidget::item:selected,QTableWidget::item:selected{{background:{accent};color:{background};}}
QSlider::handle:horizontal{{background:{accent};width:14px;border-radius:6px;}} QToolTip{{background:{panel};color:{text};border:1px solid {border};}}
'''.format(**c)
