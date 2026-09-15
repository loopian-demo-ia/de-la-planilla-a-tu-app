"""Demo administrativa Loopian. Dominio y adaptadores puros; UI al final.
No hay red, emisión fiscal, envío de correo ni almacenamiento de datos en disco.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from email.policy import SMTP
from html import escape

BASE = ['id', 'fecha', 'cliente', 'email', 'concepto', 'importe', 'estado']
EXTRA = ['tipo_registro', 'version_registro', 'id_demo', 'fecha_demo', 'errores']
DISCLAIMER = 'DEMOSTRACIÓN · Sin validez fiscal'
FISCAL_NOTE = 'La emisión fiscal requiere configurar ARCA y validar las reglas de la empresa con su contador'
EXAMPLE = '''id,fecha,cliente,email,concepto,importe,estado
V001,2026-09-03,Estudio Jacarandá (ficticio),jacaranda@example.com,Edición de videos,85000.00,pendiente
V002,2026-09-07,Café Horizonte (ficticio),horizonte@example.com,Gestión de redes,125000.50,pendiente
V003,2026-09-10,Taller Nube (ficticio),nube@example.com,Diseño de piezas,42000.00,pendiente
V003,2026-09-11,Librería Brisa (ficticia),brisa@example.com,Producción de contenido,58000.00,pendiente
V004,2026-09-14,Proyecto Lima (ficticio),lima@example.com,Edición de reel,no_es_un_importe,pendiente
'''


# 1. Dominio: nunca usar float para dinero.
def parse_money(value: str) -> Decimal:
    value = value.strip()
    if not re.fullmatch(r'\d{1,10}(?:[.,]\d{1,2})?', value):
        raise ValueError('Importe inválido: usá 85000.50 o 85000,50, sin separador de miles.')
    try:
        amount = Decimal(value.replace(',', '.'))
    except InvalidOperation as exc:
        raise ValueError('Importe inválido.') from exc
    if not amount.is_finite() or amount <= 0 or amount > Decimal('9999999999.99'):
        raise ValueError('El importe debe ser mayor que cero y hasta 9.999.999.999,99.')
    return amount.quantize(Decimal('0.01'))


def money(value: Decimal) -> str:
    return '$ ' + f'{value:,.2f}'.translate(str.maketrans(',.', '.,'))


def valid_date(value: str) -> bool:
    try:
        return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', value)) and date.fromisoformat(value).year >= 1900
    except ValueError:
        return False


def demo_id(sale_id: str) -> str:
    return 'DEMO-' + hashlib.sha256(sale_id.encode('utf-8')).hexdigest()[:20].upper()


def base_errors(row: dict) -> list[str]:
    errors = []
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,39}', row['id']):
        errors.append('ID inválido: 1 a 40 letras, números, guiones o guiones bajos.')
    if not valid_date(row['fecha']):
        errors.append('Fecha inválida: usá AAAA-MM-DD, desde 1900.')
    for field, limit in [('cliente', 120), ('concepto', 800)]:
        if not row[field] or len(row[field]) > limit:
            errors.append(f'{field.capitalize()}: completá entre 1 y {limit} caracteres.')
        # Standard PDF fonts cover Spanish and CP1252. Reject unsupported glyphs explicitly.
        try:
            row[field].encode('cp1252')
        except UnicodeEncodeError:
            errors.append(f'{field.capitalize()}: usá texto español sin emojis ni otros alfabetos.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,63}@example\.com', row['email']):
        errors.append('Email de demo: usá un destinatario ficticio @example.com.')
    try:
        parse_money(row['importe'])
    except ValueError as exc:
        errors.append(str(exc))
    if row['estado'] not in ('pendiente', 'procesada', 'error'):
        errors.append('Estado inválido: usá pendiente, procesada o error.')
    if any(any(ord(c) < 32 or ord(c) == 127 for c in row[k]) for k in BASE):
        errors.append('Quitá saltos de línea y caracteres de control dentro de las celdas.')
    return errors


def fingerprint(row: dict) -> tuple:
    return tuple(str(parse_money(row[k])) if k == 'importe' else row[k] for k in BASE[:-1])


def assess(rows: list[dict], ledger: dict) -> list[dict]:
    counts = Counter(row['id'] for row in rows)
    result = []
    for number, row in enumerate(rows, 2):
        errors = base_errors(row)
        if counts[row['id']] > 1:
            errors.append('ID repetido: se bloquean todas sus filas. Corregí el CSV y volvé a importarlo.')
        previous = ledger.get(row['id'])
        if not errors and previous and fingerprint(row) != fingerprint(previous):
            errors.append('Este ID ya tiene un comprobante con otros datos. Se conserva el original; revisá el ID.')
        if not errors and row['estado'] == 'procesada' and not previous:
            errors.append('Falta el respaldo del comprobante. Importá el registro completo, con sus filas comprobante.')
        if not errors and previous and row.get('id_demo') and row['id_demo'] != previous['id_demo']:
            errors.append('El ID demo no coincide con el comprobante conservado.')
        status = 'error' if errors else ('procesada' if previous else 'pendiente')
        result.append(dict(row=row, fila=number, errors=errors, status=status))
    return result


# 2. Adaptador CSV. Un registro incluye ventas + copias inmutables de comprobantes.
# Una futura conexión a Sheets puede entregar bytes CSV a import_csv().
def read_csv(data: bytes) -> tuple[list[dict], bool]:
    if len(data) > 2_000_000:
        raise ValueError('El archivo supera 2 MB. Dividilo en archivos más chicos.')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Guardá el archivo como CSV UTF-8.') from exc
    try:
        first_line = text.splitlines()[0] if text.splitlines() else ''
        delimiter = ';' if first_line.count(';') > first_line.count(',') else ','
        reader = csv.DictReader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or not set(BASE).issubset(headers):
            raise ValueError('Columnas requeridas, sin repetir: ' + ', '.join(BASE))
        is_record = 'tipo_registro' in headers
        if is_record and not set(EXTRA).issubset(headers):
            raise ValueError('El registro está incompleto. Conservá todas las columnas exportadas.')
        rows = []
        for row in reader:
            if len(rows) >= 5000:
                raise ValueError('Máximo 5.000 filas por archivo.')
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Hay una fila con columnas de más o de menos. Revisá comillas y separadores.')
            cleaned = {k: row.get(k, '').strip() for k in BASE + EXTRA}
            # Our exports guard spreadsheet formulas with a leading apostrophe.
            # Decode only versioned records and only that exact safety encoding.
            if is_record:
                for k, v in cleaned.items():
                    if len(v) > 1 and v[0] == "'" and v[1] in "=+-@'":
                        cleaned[k] = v[1:]
            rows.append(cleaned)
        if not rows:
            raise ValueError('El CSV está vacío. Agregá al menos una venta.')
        return rows, is_record
    except csv.Error as exc:
        raise ValueError('No se pudo leer el CSV. Revisá el formato y las comillas.') from exc


def import_csv(data: bytes, ledger: dict) -> tuple[list[dict], dict]:
    """Atomic import. Pending dataset replaced; processed history always retained."""
    entries, is_record = read_csv(data)
    merged = {k: dict(v) for k, v in ledger.items()}
    if is_record:
        if any(r['version_registro'] != '1' or r['tipo_registro'] not in ('venta', 'comprobante') for r in entries):
            raise ValueError('Versión o tipo de registro no compatible. Usá el registro original exportado.')
        snapshots = [r for r in entries if r['tipo_registro'] == 'comprobante']
        if len({r['id'] for r in snapshots}) != len(snapshots):
            raise ValueError('El respaldo contiene comprobantes duplicados. No se importó ningún cambio.')
        for row in snapshots:
            if (base_errors(row) or row['estado'] != 'procesada'
                    or row['id_demo'] != demo_id(row['id']) or not valid_date(row['fecha_demo'])):
                raise ValueError('Un respaldo de comprobante es inválido. No se importó ningún cambio.')
            snap = {k: row[k] for k in BASE + ['id_demo', 'fecha_demo']}
            snap['importe'] = str(parse_money(snap['importe']))
            old = merged.get(snap['id'])
            if old and (fingerprint(old) != fingerprint(snap) or old['id_demo'] != snap['id_demo'] or old['fecha_demo'] != snap['fecha_demo']):
                raise ValueError(f'Conflicto en el comprobante de {snap["id"]}. Se conserva la sesión sin cambios.')
            merged[snap['id']] = snap
        rows = [r for r in entries if r['tipo_registro'] == 'venta']
    else:
        rows = entries
    if not rows:
        raise ValueError('El archivo debe contener al menos una fila de venta.')
    return rows, merged


def approve(rows: list[dict], ledger: dict, index: int, confirmed: bool, today: str | None = None):
    if not confirmed:
        raise ValueError('Revisá la venta y confirmá su aprobación.')
    if not 0 <= index < len(rows):
        raise ValueError('Elegí una venta disponible.')
    checked = assess(rows, ledger)[index]
    if checked['errors']:
        raise ValueError('Esta venta tiene errores; corregila antes de preparar un comprobante.')
    row = checked['row']
    if row['id'] in ledger:
        return ledger[row['id']], False
    issued = today or datetime.now(timezone.utc).date().isoformat()  # Hosting clock; UI documents UTC.
    if not valid_date(issued):
        raise ValueError('Fecha demo inválida.')
    snapshot = {k: row[k] for k in BASE}
    snapshot.update(estado='procesada', importe=str(parse_money(row['importe'])),
                    id_demo=demo_id(row['id']), fecha_demo=issued)
    # Generate successfully BEFORE committing the state. No cache/disk is authoritative.
    build_pdf(snapshot)
    ledger[row['id']] = snapshot
    return snapshot, True


def csv_bytes(rows: list[dict], fields: list[str]) -> bytes:
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        values = {}
        for k in fields:
            value = str(row.get(k, ''))
            values[k] = "'" + value if value.startswith(('=', '+', '-', '@', "'")) else value
        writer.writerow(values)
    return stream.getvalue().encode('utf-8-sig')


def export_registry(rows: list[dict], ledger: dict) -> bytes:
    output = []
    for item in assess(rows, ledger):
        row = item['row']
        previous = ledger.get(row['id']) if item['status'] == 'procesada' else None
        output.append(dict(row, estado=item['status'], tipo_registro='venta', version_registro='1',
                           id_demo=previous['id_demo'] if previous else '',
                           fecha_demo=previous['fecha_demo'] if previous else '',
                           errores=' | '.join(item['errors'])))
    for snap in ledger.values():
        output.append(dict(snap, tipo_registro='comprobante', version_registro='1', errores=''))
    return csv_bytes(output, BASE + EXTRA)


def monthly_summary(rows: list[dict], ledger: dict, month: str) -> list[dict]:
    if not re.fullmatch(r'\d{4}-\d{2}', month) or not valid_date(month + '-01'):
        raise ValueError('Mes inválido.')
    checked = assess(rows, ledger)
    demos = [r for r in ledger.values() if r['fecha'][:7] == month]
    pending = [i['row'] for i in checked if i['status'] == 'pendiente' and i['row']['fecha'][:7] == month]
    errors = [i for i in checked if i['errors'] and valid_date(i['row']['fecha']) and i['row']['fecha'][:7] == month]
    unassigned = [i for i in checked if i['errors'] and not valid_date(i['row']['fecha'])]
    result = []
    for name, group in [('Comprobantes demo', demos), ('Ventas pendientes', pending)]:
        result.append(dict(mes=month, categoria=name, cantidad=len(group),
                           importe_ars=str(sum((parse_money(r['importe']) for r in group), Decimal('0.00'))),
                           nota='Resumen administrativo de ejemplo. Agrupado por fecha de venta. ' + DISCLAIMER))
    for name, group in [('Filas con errores del mes', errors), ('Errores sin fecha válida (todos)', unassigned)]:
        result.append(dict(mes=month if 'del mes' in name else 'sin asignar', categoria=name,
                           cantidad=len(group), importe_ars='',
                           nota='Importe excluido: no se suma ni se presenta como cero. ' + DISCLAIMER))
    return result


# 3. Adaptadores de salida. ReportLab Paragraph interpreta markup: SIEMPRE escapar CSV.
def build_pdf(snapshot: dict) -> bytes:
    import reportlab
    from pathlib import Path
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    # Vera ships with ReportLab: embedded fonts, no external downloads/assets.
    fonts = Path(reportlab.__file__).parent / 'fonts'
    if 'DemoSans' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('DemoSans', str(fonts / 'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('DemoSansBold', str(fonts / 'VeraBd.ttf')))
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    out = io.BytesIO()
    purple = colors.HexColor('#332050')
    body = ParagraphStyle('body', fontName='DemoSans', fontSize=11, leading=17, textColor=purple, spaceAfter=9)
    title = ParagraphStyle('title', parent=body, fontName='DemoSansBold', fontSize=25, leading=30, spaceAfter=16)
    small = ParagraphStyle('small', parent=body, fontSize=9, leading=14)
    def p(value, style=body):
        return Paragraph(escape(str(value), quote=True), style)
    doc = SimpleDocTemplate(out, invariant=1, pagesize=A4, rightMargin=48, leftMargin=48,
                            topMargin=65, bottomMargin=65, title='Comprobante demostrativo', author='Loopian · Demo')
    story = [p('LOOPIAN / EJEMPLO ADMINISTRATIVO', small), Spacer(1, 12),
             p('Comprobante demostrativo', title), p(DISCLAIMER), Spacer(1, 15),
             p('ID interno: ' + snapshot['id_demo']), p('Venta: ' + snapshot['id']),
             p('Fecha de venta: ' + snapshot['fecha']),
             p('Preparado el: ' + snapshot['fecha_demo'] + ' (UTC)'), Spacer(1, 15),
             p('CLIENTE FICTICIO', small), p(snapshot['cliente']), p(snapshot['email']),
             Spacer(1, 15), p('CONCEPTO', small), p(snapshot['concepto']), Spacer(1, 20)]
    total = Table([[p('Importe registrado (ARS)'), p(money(parse_money(snapshot['importe'])))]], colWidths=[300, 199])
    total.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E8F6C5')),
                              ('TOPPADDING', (0, 0), (-1, -1), 16), ('BOTTOMPADDING', (0, 0), (-1, -1), 10)]))
    story += [total, Spacer(1, 24), p('Importe copiado de la venta. No se calculan impuestos ni se decide el tratamiento de IVA.', small),
              p(FISCAL_NOTE + '.', small), p('Este documento no acredita una emisión fiscal ni un pago. Uso educativo con datos ficticios.', small)]
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFillColor(purple)
        canvas.setFont('DemoSansBold', 9)
        canvas.drawString(48, 36, DISCLAIMER)
        canvas.drawRightString(A4[0] - 48, 36, str(document.page))
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


def build_email(snapshot: dict) -> bytes:
    message = EmailMessage(policy=SMTP)
    message['From'] = 'Loopian Demo <demo@example.com>'
    message['To'] = snapshot['email']
    message['Subject'] = 'Comprobante demostrativo ' + snapshot['id_demo']
    message['X-Unsent'] = '1'
    message.set_content('Hola, ' + snapshot['cliente'] + ':\n\nAdjuntamos un comprobante demostrativo de la venta '
                        + snapshot['id'] + '.\n\n' + DISCLAIMER + '\n'
                        + 'Este correo está preparado como ejemplo; la aplicación no lo envió.\n'
                        + FISCAL_NOTE + '.\n\nLoopian · Demo educativa')
    message.add_attachment(build_pdf(snapshot), maintype='application', subtype='pdf', filename=snapshot['id_demo'] + '.pdf')
    return message.as_bytes()


# 4. UI Streamlit. Los únicos datos mutables están en session_state.
def main():
    import pandas as pd
    import streamlit as st
    st.set_page_config(page_title='De la venta al comprobante · Loopian', page_icon='🟣', layout='wide')
    st.markdown('''<style>
    .stApp {background:#faf9fc;color:#302044;font-family:Inter,ui-sans-serif,system-ui,sans-serif;}
    .block-container {max-width:1120px;padding-top:5.2rem;padding-bottom:3rem;}
    h1,h2,h3 {color:#332050!important;letter-spacing:-.035em;}
    h1 {font-size:clamp(2rem,4vw,3.1rem)!important;line-height:1.12!important;}
    .demo-banner {position:fixed;top:0;left:0;width:100%;z-index:999999;background:#332050;
      color:#e8f6c5;text-align:center;padding:12px 8px;font-size:13px;font-weight:750;letter-spacing:.06em;}
    .eyebrow {font-weight:750;font-size:12px;letter-spacing:.14em;color:#665078;margin-bottom:12px;}
    .intro {color:#6f627d;font-size:17px;max-width:700px;line-height:1.6;}
    .steps {display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:26px 0;}
    .step {padding:17px;border:1px solid #e2dbea;background:white;border-radius:14px;font-size:14px;font-weight:650;}
    .step b {display:inline-grid;place-items:center;width:28px;height:28px;background:#d5f58a;color:#332050;border-radius:50%;margin-right:7px;}
    .cards {display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:18px 0 24px;}
    .card {padding:22px;background:#fff;border:1px solid #e8e1ee;border-radius:18px;}
    .card .label {color:#746880;font-size:13px;margin-bottom:7px;}
    .card .value {font-size:27px;font-weight:750;line-height:1.3;}
    .card .sub {font-size:12px;color:#746880;margin-top:8px;}
    button[kind="primary"],button[kind="primaryFormSubmit"] {background:#332050!important;color:white!important;border-color:#332050!important;}
    [data-testid="stDownloadButton"] button {border-radius:10px;border-color:#cabbd9;}
    [data-testid="stVerticalBlockBorderWrapper"] {border-radius:16px;}
    [data-testid="stHeader"] {top:42px;background:transparent;}
    @media(max-width:640px) {
      .block-container {padding-top:6rem;padding-left:1rem;padding-right:1rem;}
      .steps {grid-template-columns:1fr;gap:7px;margin:20px 0;}.step {padding:10px 13px;}
      .cards {grid-template-columns:1fr;gap:9px;}.card {padding:15px 18px;}.card .value{font-size:24px;}
      .demo-banner {font-size:11px;padding:12px 5px;}
    }
    </style><div class="demo-banner">DEMOSTRACIÓN · Sin validez fiscal</div>''', unsafe_allow_html=True)
    if 'ledger' not in st.session_state:
        st.session_state.rows, st.session_state.ledger = import_csv(EXAMPLE.encode(), {})
        st.session_state.source = 'Ejemplo incorporado · septiembre 2026'
        st.session_state.original = EXAMPLE.encode('utf-8-sig')
        st.session_state.generation = 0
    state = st.session_state
    if 'flash' in state:
        st.success(state.pop('flash'))
    st.markdown('<div class="eyebrow">LOOPIAN / DE LA PLANILLA A UNA HERRAMIENTA</div>', unsafe_allow_html=True)
    st.title('De la venta al comprobante')
    st.markdown('<p class="intro">Revisá tus ventas, prepará comprobantes de ejemplo y cerrá el mes con todo a mano.</p>', unsafe_allow_html=True)
    st.markdown('<div class="steps"><div class="step"><b>1</b> Revisar ventas</div><div class="step"><b>2</b> Preparar comprobantes</div><div class="step"><b>3</b> Resumen mensual</div></div>', unsafe_allow_html=True)
    st.info('Esta demo usa memoria de sesión. Descargá el registro actualizado para conservarlo y reimportarlo. Recargar la página o cerrar la sesión puede borrar los cambios.')
    st.caption(FISCAL_NOTE + '.')
    with st.expander('Cargar CSV o recuperar un registro · ayuda y ejemplo'):
        st.write('Usá datos ficticios. Importar reemplaza las ventas en revisión y conserva los comprobantes ya preparados en esta sesión. Descargá el registro antes de cambiar de archivo.')
        upload = st.file_uploader('Elegí un CSV de ventas o un registro actualizado', type=['csv'], key=f'upload_{state.generation}')
        if st.button('Importar CSV', disabled=upload is None):
            try:
                data = upload.getvalue()
                rows, ledger = import_csv(data, state.ledger)
                state.rows, state.ledger = rows, ledger
                state.original, state.source = data, upload.name
                state.generation += 1
                state.flash = 'Archivo importado. Revisá los errores antes de aprobar.'
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        st.download_button('Descargar ventas de ejemplo', EXAMPLE.encode('utf-8-sig'), 'ventas_ejemplo.csv', 'text/csv')
        st.caption('Columnas: ' + ', '.join(BASE) + '. Fechas AAAA-MM-DD; importes sin miles y con hasta 2 decimales. Máximo 2 MB / 5.000 filas. Se acepta coma o punto y coma como separador.')
        st.write('**Google Sheets:** Archivo → Descargar → Valores separados por comas (.csv, hoja actual). Para llevar el resultado de vuelta: Archivo → Importar → Subir → Insertar hojas nuevas. Conservá todas las columnas y las filas de tipo comprobante; son el respaldo para reconstruir los PDF. Para ver sólo ventas, filtrá tipo_registro = venta. No hay sincronización automática.')
        st.write('**Para reiniciar la grabación:** primero descargá el registro si querés conservarlo.')
        confirmed_reset = st.checkbox('Confirmo borrar los cambios de esta sesión y volver a las 5 filas del ejemplo', key=f'reset_{state.generation}')
        if st.button('Restablecer ejemplo', disabled=not confirmed_reset):
            state.rows, state.ledger = import_csv(EXAMPLE.encode(), {})
            state.original, state.source = EXAMPLE.encode('utf-8-sig'), 'Ejemplo incorporado · septiembre 2026'
            state.generation += 1
            state.flash = 'Ejemplo restablecido.'
            st.rerun()
    checked = assess(state.rows, state.ledger)
    pending = [i for i in checked if i['status'] == 'pendiente']
    errors = [i for i in checked if i['errors']]
    pending_amount = sum((parse_money(i['row']['importe']) for i in pending), Decimal('0.00'))
    demo_amount = sum((parse_money(r['importe']) for r in state.ledger.values()), Decimal('0.00'))
    st.markdown(f'''<div class="cards">
    <div class="card"><div class="label">Ventas pendientes válidas</div><div class="value">{money(pending_amount)}</div><div class="sub">{len(pending)} ventas listas para revisar</div></div>
    <div class="card"><div class="label">Comprobantes demo conservados</div><div class="value">{money(demo_amount)}</div><div class="sub">{len(state.ledger)} comprobantes · todos los meses</div></div>
    <div class="card"><div class="label">Filas que necesitan revisión</div><div class="value">{len(errors)}</div><div class="sub">Sus importes se excluyen de los totales</div></div></div>''', unsafe_allow_html=True)
    st.subheader('1. Revisar ventas')
    st.caption('Archivo activo: ' + state.source)
    view = []
    for i in checked:
        r = i['row']
        view.append({'Fila': i['fila'], 'ID': r['id'], 'Fecha': r['fecha'], 'Cliente': r['cliente'],
                     'Importe (ARS)': r['importe'], 'Estado': {'pendiente': 'Pendiente', 'procesada': 'Procesada', 'error': 'Revisar'}[i['status']],
                     'Observación': ' | '.join(i['errors']) or 'Sin errores'})
    st.dataframe(pd.DataFrame(view), hide_index=True, width='stretch')
    if errors:
        st.warning(f'{len(errors)} filas bloqueadas. Corregí el archivo de origen y volvé a importarlo; no se elige automáticamente entre IDs repetidos.')
        with st.expander('Ver qué corregir', expanded=True):
            for i in errors:
                st.text(f'Fila {i["fila"]} · {i["row"]["id"] or "Sin ID"}: ' + ' '.join(i['errors']))
    st.download_button('Descargar CSV original', state.original, 'ventas_original.csv', 'text/csv')
    st.subheader('2. Preparar comprobantes')
    st.caption('Elegí una venta y aprobala expresamente. No se calcula IVA ni se autoriza una factura.')
    indices = [idx for idx, i in enumerate(checked) if i['status'] == 'pendiente']
    if indices:
        index = st.selectbox('Venta para revisar', indices,
                             format_func=lambda n, sales=state.rows: sales[n]['id'] + ' · ' + sales[n]['cliente'],
                             key=f'selection_{state.generation}')
        r = state.rows[index]
        with st.container(border=True):
            st.text(f'{r["cliente"]}\n{r["email"]}\nFecha de venta: {r["fecha"]}')
            st.text(r['concepto'])
            st.metric('Importe registrado · ARS', money(parse_money(r['importe'])))
            with st.form(f'approve_{state.generation}_{r["id"]}'):
                confirm = st.checkbox('Revisé los datos y apruebo esta venta para un comprobante DEMOSTRATIVO')
                submit = st.form_submit_button('Aprobar y generar comprobante demo', type='primary')
            if submit:
                try:
                    snap, created = approve(state.rows, state.ledger, index, confirm)
                    state.last_demo = snap['id']
                    state.generation += 1
                    state.flash = 'Comprobante demo preparado. Descargá el PDF, el correo y el registro actualizado.' if created else 'Este comprobante ya existe. Podés volver a descargarlo.'
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    else:
        st.info('No hay ventas válidas pendientes. Revisá los errores o descargá los comprobantes disponibles.')
    if state.ledger:
        ids = list(state.ledger)
        default = ids.index(state.last_demo) if state.get('last_demo') in ids else 0
        selected = st.selectbox('Comprobantes disponibles para descargar', ids, index=default,
                                format_func=lambda k, history=state.ledger: k + ' · ' + history[k]['cliente'])
        snap = state.ledger[selected]
        st.caption(snap['id_demo'] + ' · Preparado el ' + snap['fecha_demo'] + ' (UTC). Volver a descargar conserva el mismo ID.')
        st.download_button('Descargar PDF demo', build_pdf(snap), snap['id_demo'] + '.pdf', 'application/pdf')
        st.download_button('Descargar correo preparado', build_email(snap), snap['id_demo'] + '.eml', 'message/rfc822')
        st.caption('El .eml incluye el PDF adjunto. Podés abrirlo en un cliente de correo compatible. La app no envía correos.')
    st.subheader('3. Resumen mensual')
    st.caption('Resumen administrativo de ejemplo · agrupado por mes de la venta, no por fecha de preparación. Los comprobantes conservados se cuentan una sola vez, aunque cargues otro CSV.')
    months = sorted({r['fecha'][:7] for r in state.rows + list(state.ledger.values()) if valid_date(r['fecha'])}, reverse=True)
    month = st.selectbox('Mes de las ventas', months or [date.today().strftime('%Y-%m')])
    summary = monthly_summary(state.rows, state.ledger, month)
    st.dataframe(pd.DataFrame([{'Categoría': r['categoria'], 'Cantidad': r['cantidad'],
                               'Importe (ARS)': money(Decimal(r['importe_ars'])) if r['importe_ars'] else 'Excluido'} for r in summary]),
                 hide_index=True, width='stretch')
    st.caption('Errores = cantidad de filas, no cantidad de mensajes. Las fechas inválidas se informan aparte, sin asignarlas a un mes. Los importes de errores no se suman.')
    st.download_button('Descargar resumen mensual CSV', csv_bytes(summary, ['mes', 'categoria', 'cantidad', 'importe_ars', 'nota']),
                       f'resumen_administrativo_{month}.csv', 'text/csv')
    st.download_button('Descargar registro actualizado CSV', export_registry(state.rows, state.ledger),
                       'registro_actualizado.csv', 'text/csv', type='primary')
    st.caption('Guardá este registro completo: contiene ventas y filas de respaldo de comprobantes. Reimportalo para recuperar estados, IDs y PDF. No es una base fiscal ni un archivo firmado.')
    st.divider()
    st.caption(DISCLAIMER + ' · Hecho para aprender con Loopian. Sin conexión a Sheets o ARCA, sin tareas automáticas y sin APIs pagas.')


if __name__ == '__main__':
    main()
