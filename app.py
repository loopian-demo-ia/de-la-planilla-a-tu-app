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
            errors.append('ID repetido: se bloquean todas sus filas. Asigná un ID distinto desde el formulario de corrección.')
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


def correct_sale(rows: list[dict], ledger: dict, index: int, changes: dict) -> list[dict]:
    """Return an independently validated copy. Never mutate rows or the ledger.

    Index identifies the source row even when its ID is duplicated. Validation
    is repeated at commit time; UI availability alone never grants editability.
    """
    if not isinstance(index, int) or not 0 <= index < len(rows):
        raise ValueError('Elegí una fila disponible.')
    original = rows[index]
    if original['id'] in ledger:
        raise ValueError('Esta venta tiene un comprobante conservado y no se puede editar.')
    editable = set(BASE[:-1])
    if not changes or set(changes) - editable or any(not isinstance(v, str) for v in changes.values()):
        raise ValueError('Sólo podés corregir ID, fecha, cliente, email, concepto e importe.')
    candidate = {k: original.get(k, '') for k in BASE + EXTRA}
    candidate.update({k: v.strip() for k, v in changes.items()})
    if candidate['id'] in ledger:
        raise ValueError('Ese ID pertenece a un comprobante conservado. Elegí otro ID.')
    if any(n != index and row['id'] == candidate['id'] for n, row in enumerate(rows)):
        raise ValueError('Ese ID ya aparece en otra venta. Elegí un ID único.')
    candidate.update(estado='pendiente', id_demo='', fecha_demo='', errores='')
    errors = base_errors(candidate)
    if errors:
        raise ValueError(' '.join(errors))
    candidate['importe'] = str(parse_money(candidate['importe']))
    updated = [dict(row) for row in rows]
    updated[index] = candidate
    # Reassess the entire batch: resolving a duplicate releases BOTH valid rows.
    checked = assess(updated, ledger)
    if checked[index]['errors']:
        raise ValueError(' '.join(checked[index]['errors']))
    for item in checked:
        item['row']['estado'] = item['status']
        item['row']['errores'] = ' | '.join(item['errors'])
    return updated


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
CSS = '''<style>
.stApp {background:#faf9fc;color:#302044;font-family:Inter,ui-sans-serif,system-ui,sans-serif;}
.block-container {max-width:1050px;padding-top:4.3rem;padding-bottom:2rem;}
h1,h2,h3 {color:#332050!important;letter-spacing:-.035em;}
h1 {font-size:clamp(1.6rem,3.5vw,2.3rem)!important;line-height:1.15!important;padding:0 0 .35rem!important;}
h3 {font-size:1.2rem!important;}
.demo-banner {position:fixed;top:0;left:0;width:100%;z-index:999999;background:#332050;color:#e8f6c5;
  text-align:center;padding:10px 6px;font-size:12px;font-weight:750;letter-spacing:.035em;}
.eyebrow {font-size:11px;font-weight:750;letter-spacing:.12em;color:#786487;margin-bottom:4px;}
.stats {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 8px;}
.stat {background:white;border:1px solid #e4dceb;border-radius:12px;padding:10px 14px;min-width:0;}
.stat b {display:block;font-size:23px;color:#332050;line-height:1.2;}
.stat span {font-size:12px;color:#695b76;}
.mini-note {font-size:12px;color:#766784;margin:4px 0 8px;}
.sale-card {padding:14px 16px;background:#fff;border:1px solid #e4dceb;border-radius:12px;margin:7px 0;
  overflow-wrap:anywhere;}
.sale-card .meta {font-size:12px;color:#766784;margin-bottom:5px;}
.sale-card .amount {font-size:19px;font-weight:700;margin:5px 0;}
.sale-card .issue {font-size:13px;color:#83480b;margin-top:5px;}
.sale-card .ok {font-size:13px;color:#49651e;}
button[kind="primary"],button[kind="primaryFormSubmit"] {background:#332050!important;color:white!important;border-color:#332050!important;}
[data-testid="stDownloadButton"] button {border-radius:9px;border-color:#cabbd9;}
[data-testid="stHeader"] {top:36px;background:transparent;}
[data-baseweb="tab-list"] {gap:6px;width:100%;}
button[data-baseweb="tab"] {flex:1;min-width:0;padding:8px 4px;min-height:44px;}
button[data-baseweb="tab"][aria-selected="true"] {color:#332050;background:#e8f6c5;border-radius:9px 9px 0 0;}
[data-testid="stText"] {white-space:pre-wrap;overflow-wrap:anywhere;}
[data-testid="stText"] pre {white-space:pre-wrap;overflow-wrap:anywhere;}
.mobile-sales {display:none;}
@media(max-width:640px) {
  .block-container {padding-top:4.2rem;padding-left:1rem;padding-right:1rem;}
  .demo-banner {font-size:11px;}
  [data-testid="stHeader"] {height:24px;}
  .stat {padding:8px 9px;}.stat b {font-size:21px;}.stat span {font-size:11px;}
  button[data-baseweb="tab"] p {font-size:13px;white-space:nowrap;}
  [data-testid="stFormSubmitButton"] button,[data-testid="stDownloadButton"] button {width:100%;min-height:44px;}
  .st-key-sales-table {display:none;}.mobile-sales {display:block;}
  [data-testid="stTextInput"] input {font-size:16px;}
}
</style><div class="demo-banner">DEMOSTRACIÓN · Sin validez fiscal</div>'''


def render_help(st):
    with st.expander('Cómo funciona'):
        st.write('**1 · Revisar:** cargá un CSV o usá el ejemplo. Elegí una fila y corregí sus datos. Sólo se guarda si queda válida. Las ventas con comprobante están bloqueadas.')
        st.write('**2 · Preparar:** revisá y aprobá cada venta. Descargá su PDF demo o el correo preparado con el PDF adjunto. No se envía ningún correo.')
        st.write('**3 · Resumen:** elegí el mes y descargá el resumen administrativo de ejemplo. Los errores no suman importes.')
        st.write('**Guardá tu trabajo:** la app usa memoria de sesión. Una recarga completa, desconexión o reinicio puede borrar los cambios. Descargá el registro actualizado y reimportalo para recuperar estados, IDs y PDF. El CSV original no incluye correcciones de pantalla.')
        st.write(FISCAL_NOTE + '. No se calcula IVA ni se emiten facturas autorizadas.')
        st.write('**CSV:** ' + ', '.join(BASE) + '. UTF-8, separado por comas o punto y coma. Fecha AAAA-MM-DD. Importe sin miles, con hasta 2 decimales. Máximo 2 MB y 5.000 filas; sólo datos ficticios y correos @example.com.')
        st.write('**Google Sheets:** Archivo → Descargar → Valores separados por comas. Para devolver el registro: Archivo → Importar → Subir → Insertar hojas nuevas. Conservá todas las columnas y filas de tipo comprobante: son el respaldo. Filtrá tipo_registro = venta para ver sólo ventas. No sumes ambos tipos juntos.')
        st.caption('Sin conexión a Sheets o ARCA, sin ejecución automática 24/7 y sin almacenamiento permanente en el servidor. El respaldo no está firmado ni autenticado.')


def save_correction_callback(index, generation, keys):
    import streamlit as st
    state = st.session_state
    try:
        if state.generation != generation:
            raise ValueError('Los datos cambiaron. Volvé a elegir la fila.')
        changes = {field: state[key] for field, key in keys.items()}
        state.rows = correct_sale(state.rows, state.ledger, index, changes)
        state.generation += 1
        state.flash = 'Corrección guardada. Podés aprobar la venta en «2 · Preparar».'
    except ValueError as exc:
        state.correction_error = str(exc)


def approve_callback(index, generation, confirmation_key):
    import streamlit as st
    state = st.session_state
    try:
        if state.generation != generation:
            raise ValueError('Los datos cambiaron. Volvé a revisar la venta.')
        snap, created = approve(state.rows, state.ledger, index, state[confirmation_key])
        state.last_demo = snap['id']
        state.generation += 1
        state.flash = 'Comprobante demo preparado. Ya podés descargarlo.' if created else 'El comprobante ya existe. Podés descargarlo otra vez.'
    except ValueError as exc:
        state.approval_error = str(exc)


def render_correction(st, state, checked):
    editable = [n for n, item in enumerate(checked) if item['row']['id'] not in state.ledger]
    st.subheader('Corregir una venta')
    if not editable:
        st.info('Las ventas de este archivo tienen comprobantes conservados. No se pueden editar.')
        return
    # First error by default. The row number disambiguates repeated IDs.
    first = next((n for n in editable if checked[n]['errors']), editable[0])
    index = st.selectbox('Fila para corregir', editable, index=editable.index(first),
                         format_func=lambda n, sales=state.rows: f'Fila {n + 2} · {sales[n]["id"] or "Sin ID"} · {sales[n]["cliente"]}',
                         key=f'edit_selection_{state.generation}')
    row = state.rows[index]
    if checked[index]['errors']:
        st.warning(' '.join(checked[index]['errors']))
    st.caption('El ID debe ser único. Guardar una corrección no aprueba la venta.')
    keys = {field: f'edit_{state.generation}_{index}_{field}' for field in BASE[:-1]}
    with st.form(f'correction_{state.generation}_{index}'):
        left, right = st.columns(2)
        with left:
            st.text_input('ID de venta', value=row['id'], key=keys['id'])
        with right:
            st.text_input('Fecha de venta', value=row['fecha'], help='Formato AAAA-MM-DD.', key=keys['fecha'])
        st.text_input('Cliente ficticio', value=row['cliente'], key=keys['cliente'])
        st.text_input('Email de ejemplo', value=row['email'], key=keys['email'])
        st.text_input('Concepto', value=row['concepto'], key=keys['concepto'])
        st.text_input('Importe en pesos', value=row['importe'], help='Ejemplo: 85000,50. Sin separadores de miles.', key=keys['importe'])
        st.form_submit_button('Guardar corrección', type='primary', on_click=save_correction_callback,
                              args=(index, state.generation, keys))
    if 'correction_error' in state:
        st.error(state.pop('correction_error'))
    if any(r['id'] in state.ledger for r in state.rows):
        st.caption('Las filas con un ID que tiene comprobante quedan fuera del formulario, incluso si presentan errores.')


def main():
    import pandas as pd
    import streamlit as st
    st.set_page_config(page_title='De la venta al comprobante · Loopian', page_icon='🟣', layout='wide')
    st.markdown(CSS, unsafe_allow_html=True)
    if 'ledger' not in st.session_state:
        st.session_state.rows, st.session_state.ledger = import_csv(EXAMPLE.encode(), {})
        st.session_state.source = 'Ejemplo incorporado · septiembre 2026'
        st.session_state.original = EXAMPLE.encode('utf-8-sig')
        st.session_state.generation = 0
    state = st.session_state
    st.markdown('<div class="eyebrow">LOOPIAN / DEMO ADMINISTRATIVA</div>', unsafe_allow_html=True)
    st.title('De la venta al comprobante')
    st.caption('Sólo memoria de sesión: descargá el registro para conservar los cambios.')
    render_help(st)
    flash = st.empty()  # Keep the tab container in a stable position across reruns.
    if 'flash' in state:
        flash.success(state.pop('flash'))
    review_tab, prepare_tab, summary_tab = st.tabs(['1 · Revisar', '2 · Preparar', '3 · Resumen'], key='workflow')
    checked = assess(state.rows, state.ledger)
    pending = [i for i in checked if i['status'] == 'pendiente']
    errors = [i for i in checked if i['errors']]
    with review_tab:
        st.markdown(f'<div class="stats"><div class="stat"><b>{len(pending)}</b><span>Pendientes</span></div>'
                    f'<div class="stat"><b>{len(state.ledger)}</b><span>Demo conservados</span></div>'
                    f'<div class="stat"><b>{len(errors)}</b><span>Con errores</span></div></div>', unsafe_allow_html=True)
        st.caption('Archivo: ' + state.source)
        with st.expander('Cargar CSV o recuperar registro'):
            st.caption('Reemplaza las ventas en revisión y conserva los comprobantes de esta sesión. Descargá antes tu registro.')
            upload = st.file_uploader('Elegí un CSV', type=['csv'], key=f'upload_{state.generation}')
            if st.button('Importar CSV', disabled=upload is None):
                try:
                    data = upload.getvalue()
                    rows, ledger = import_csv(data, state.ledger)
                    state.rows, state.ledger = rows, ledger
                    state.original, state.source = data, upload.name
                    state.generation += 1
                    state.flash = 'Archivo importado. Revisá las ventas.'
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            st.download_button('Descargar ventas de ejemplo', EXAMPLE.encode('utf-8-sig'), 'ventas_ejemplo.csv', 'text/csv')
        render_correction(st, state, checked)
        with st.expander('Ver todas las ventas'):
            view = []
            cards = []
            for item in checked:
                r = item['row']
                status = {'pendiente': 'Pendiente', 'procesada': 'Procesada', 'error': 'Revisar'}[item['status']]
                view.append({'Fila': item['fila'], 'ID': r['id'], 'Fecha': r['fecha'], 'Cliente': r['cliente'],
                             'Importe (ARS)': r['importe'], 'Estado': status, 'Observación': ' | '.join(item['errors']) or 'Sin errores'})
                # All CSV text is escaped before inserting into the mobile HTML cards.
                details = escape(' '.join(item['errors'])) if item['errors'] else 'Sin errores'
                cards.append(f'<div class="sale-card"><div class="meta">Fila {item["fila"]} · {escape(r["id"])} · {escape(status)}</div>'
                             f'<strong>{escape(r["cliente"])}</strong><div class="meta">{escape(r["fecha"])}</div>'
                             f'<div class="amount">ARS {escape(r["importe"])}</div><div class="issue">{details}</div></div>')
            with st.container(key='sales-table'):
                st.dataframe(pd.DataFrame(view), hide_index=True, width='stretch')
            st.markdown('<div class="mobile-sales">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
        st.download_button('Descargar CSV original', state.original, 'ventas_original.csv', 'text/csv')
        with st.expander('Restablecer el ejemplo'):
            st.caption('Descargá el registro antes si querés conservar los cambios.')
            confirmed_reset = st.checkbox('Confirmo borrar los cambios de esta sesión y volver a las 5 filas del ejemplo', key=f'reset_{state.generation}')
            if st.button('Restablecer ejemplo', disabled=not confirmed_reset):
                state.rows, state.ledger = import_csv(EXAMPLE.encode(), {})
                state.original, state.source = EXAMPLE.encode('utf-8-sig'), 'Ejemplo incorporado · septiembre 2026'
                state.generation += 1
                state.flash = 'Ejemplo restablecido.'
                st.rerun()
    with prepare_tab:
        st.subheader('Preparar un comprobante demo')
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
                confirmation_key = f'confirm_{state.generation}_{r["id"]}'
                with st.form(f'approve_{state.generation}_{r["id"]}'):
                    st.checkbox('Revisé los datos y apruebo esta venta para un comprobante DEMOSTRATIVO', key=confirmation_key)
                    st.form_submit_button('Aprobar y generar comprobante demo', type='primary',
                                          on_click=approve_callback, args=(index, state.generation, confirmation_key))
                if 'approval_error' in state:
                    st.error(state.pop('approval_error'))
        else:
            st.info('No hay ventas válidas pendientes. Revisá «1 · Revisar».')
        if state.ledger:
            st.subheader('Descargar comprobantes')
            ids = list(state.ledger)
            default = ids.index(state.last_demo) if state.get('last_demo') in ids else 0
            selected = st.selectbox('Comprobantes disponibles para descargar', ids, index=default,
                                    format_func=lambda k, history=state.ledger: k + ' · ' + history[k]['cliente'])
            snap = state.ledger[selected]
            st.caption(snap['id_demo'] + ' · ' + snap['fecha_demo'] + ' (UTC)')
            st.download_button('Descargar PDF demo', build_pdf(snap), snap['id_demo'] + '.pdf', 'application/pdf')
            st.download_button('Descargar correo preparado', build_email(snap), snap['id_demo'] + '.eml', 'message/rfc822')
            st.caption('El correo incluye el PDF adjunto. La app no lo envía.')
    with summary_tab:
        st.subheader('Resumen mensual')
        st.caption('Resumen administrativo de ejemplo, por mes de la venta.')
        months = sorted({r['fecha'][:7] for r in state.rows + list(state.ledger.values()) if valid_date(r['fecha'])}, reverse=True)
        month = st.selectbox('Mes de las ventas', months or [date.today().strftime('%Y-%m')])
        summary = monthly_summary(state.rows, state.ledger, month)
        for item in summary:
            amount = money(Decimal(item['importe_ars'])) if item['importe_ars'] else 'Importe excluido'
            st.markdown(f'<div class="sale-card"><div class="meta">{escape(item["categoria"])}</div>'
                        f'<strong>{item["cantidad"]} registros</strong><div class="amount">{escape(amount)}</div></div>', unsafe_allow_html=True)
        st.caption('Errores por fila. Las fechas inválidas se informan aparte. Cada comprobante se cuenta una sola vez.')
        st.download_button('Descargar resumen mensual CSV', csv_bytes(summary, ['mes', 'categoria', 'cantidad', 'importe_ars', 'nota']),
                           f'resumen_administrativo_{month}.csv', 'text/csv')
    # Always reachable from any tab, with up-to-date corrections and immutable snapshots.
    st.download_button('Descargar registro actualizado CSV', export_registry(state.rows, state.ledger),
                       'registro_actualizado.csv', 'text/csv', type='primary', width='stretch')
    st.caption('Tu respaldo completo para recuperar ventas y comprobantes.')


if __name__ == '__main__':
    main()
