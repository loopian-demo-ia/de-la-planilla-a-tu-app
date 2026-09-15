"""Ejecutar: python -m unittest -v test_app.py (sin pytest)."""
import copy
import csv
import io
import unittest
from decimal import Decimal
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch

import app


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.ledger = app.import_csv(app.EXAMPLE.encode(), {})

    def process(self):
        return app.approve(self.rows, self.ledger, 0, True, '2026-09-15')[0]

    def test_duplicate_and_invalid_amount_excluded(self):
        checked = app.assess(self.rows, self.ledger)
        self.assertEqual([r['status'] for r in checked], ['pendiente', 'pendiente', 'error', 'error', 'error'])
        summary = app.monthly_summary(self.rows, self.ledger, '2026-09')
        self.assertEqual(summary[1]['importe_ars'], '210000.50')
        self.assertEqual(summary[2]['cantidad'], 3)
        self.assertEqual(summary[2]['importe_ars'], '')
        for index in [2, 3, 4]:
            with self.assertRaises(ValueError):
                app.approve(self.rows, self.ledger, index, True)
        self.assertFalse(self.ledger)

    def test_explicit_approval_and_idempotency(self):
        with self.assertRaises(ValueError):
            app.approve(self.rows, self.ledger, 0, False)
        first = self.process()
        second, created = app.approve(self.rows, self.ledger, 0, True, '2026-09-16')
        self.assertFalse(created)
        self.assertEqual(first, second)
        self.assertEqual(len(self.ledger), 1)

    def test_reimport_original_keeps_processed(self):
        snap = self.process()
        rows, ledger = app.import_csv(app.EXAMPLE.encode(), self.ledger)
        again, created = app.approve(rows, ledger, 0, True)
        self.assertFalse(created)
        self.assertEqual(again, snap)

    def test_registry_restores_new_session_and_pdf(self):
        snap = self.process()
        pdf = app.build_pdf(snap)
        backup = app.export_registry(self.rows, self.ledger)
        rows, ledger = app.import_csv(backup, {})
        self.assertEqual(app.assess(rows, ledger)[0]['status'], 'procesada')
        self.assertEqual(ledger['V001'], snap)
        self.assertEqual(app.build_pdf(ledger['V001']), pdf)
        self.assertFalse(app.approve(rows, ledger, 0, True)[1])
        self.assertEqual(app.export_registry(rows, ledger), backup)

    def test_import_conflict_is_atomic(self):
        self.process()
        original = copy.deepcopy(self.ledger)
        backup = app.export_registry(self.rows, self.ledger).replace(b'85000.00', b'85001.00')
        with self.assertRaises(ValueError):
            app.import_csv(backup, self.ledger)
        self.assertEqual(self.ledger, original)

    def test_changed_sale_cannot_overwrite_processed(self):
        snap = self.process()
        rows, ledger = app.import_csv(app.EXAMPLE.replace('85000.00', '90000.00').encode(), self.ledger)
        self.assertEqual(app.assess(rows, ledger)[0]['status'], 'error')
        with self.assertRaises(ValueError):
            app.approve(rows, ledger, 0, True)
        self.assertEqual(ledger['V001'], snap)
        rows2, ledger2 = app.import_csv(app.export_registry(rows, ledger), {})
        self.assertEqual(ledger2['V001'], snap)
        self.assertEqual(app.assess(rows2, ledger2)[0]['status'], 'error')

    def test_history_survives_switching_csv(self):
        snap = self.process()
        data = app.EXAMPLE.splitlines()[0] + '\n' + app.EXAMPLE.splitlines()[2] + '\n'
        rows, ledger = app.import_csv(data.encode(), self.ledger)
        self.assertEqual(len(rows), 1)
        rows, ledger = app.import_csv(app.export_registry(rows, ledger), {})
        self.assertEqual(ledger['V001'], snap)
        self.assertEqual(app.monthly_summary(rows, ledger, '2026-09')[0]['cantidad'], 1)

    def test_processing_requires_successful_pdf(self):
        with patch.object(app, 'build_pdf', side_effect=ValueError('PDF falló')):
            with self.assertRaises(ValueError):
                self.process()
        self.assertFalse(self.ledger)

    def test_decimal_strict_inputs(self):
        for value in ['NaN', 'Infinity', '-5', '0', '1e4', '1.234', '1.234,56', '', '10000000000']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                app.parse_money(value)
        self.assertEqual(app.parse_money('0,10') + app.parse_money('0.20'), Decimal('0.30'))

    def test_malformed_files(self):
        for data in [b'', b'id,fecha\n1,2026-09-15', b'\xff', app.EXAMPLE.encode() + b'1,2\n', b'x' * 2_000_001]:
            with self.subTest(data=data[:30]), self.assertRaises(ValueError):
                app.import_csv(data, {})

    def test_semicolon_and_decimal_comma(self):
        data = ';'.join(app.BASE) + '\nV9;2026-09-01;Cliente;cliente@example.com;Concepto;23,45;pendiente\n'
        rows, ledger = app.import_csv(data.encode(), {})
        self.assertFalse(app.assess(rows, ledger)[0]['errors'])
        self.assertEqual(app.parse_money(rows[0]['importe']), Decimal('23.45'))

    def test_unbacked_processed_state_blocked(self):
        rows, ledger = app.import_csv(app.EXAMPLE.replace('pendiente', 'procesada', 1).encode(), {})
        self.assertEqual(app.assess(rows, ledger)[0]['status'], 'error')

    def test_pdf_escapes_csv_markup(self):
        self.rows[0]['concepto'] = '<b>Literal</b> & <img src="https://example.com/x"/> ' + 'Texto ' * 70
        snapshot = self.process()
        pdf = app.build_pdf(snapshot)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        # Optional text check with pypdf when installed in the review environment.
        try:
            from pypdf import PdfReader
        except ImportError:
            return
        text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        self.assertIn('<b>Literal</b>', text)
        self.assertIn(app.DISCLAIMER, text)
        self.assertIn(snapshot['id_demo'], text)

    def test_eml_has_exact_pdf_attachment_and_no_send(self):
        snap = self.process()
        message = BytesParser(policy=policy.default).parsebytes(app.build_email(snap))
        attachments = list(message.iter_attachments())
        self.assertEqual(message['To'], 'jacaranda@example.com')
        self.assertEqual(message['X-Unsent'], '1')
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_content_type(), 'application/pdf')
        self.assertEqual(attachments[0].get_payload(decode=True), app.build_pdf(snap))
        self.assertIn(app.DISCLAIMER, message.get_body().get_content())

    def test_formula_guard_roundtrip(self):
        self.rows[0]['concepto'] = '=SUM(1+1)'
        self.rows[0]['cliente'] = "'Cliente ficticio"
        snap = self.process()
        backup = app.export_registry(self.rows, self.ledger)
        self.assertIn(b"'=SUM(1+1)", backup)
        rows, ledger = app.import_csv(backup, {})
        self.assertEqual(rows[0]['concepto'], '=SUM(1+1)')
        self.assertEqual(ledger['V001'], snap)

    def test_invalid_dates_and_email(self):
        self.rows[4]['fecha'] = '2026-99-99'
        self.rows[1]['email'] = 'persona@dominio-real.com'
        summary = app.monthly_summary(self.rows, self.ledger, '2026-09')
        self.assertEqual(summary[3]['cantidad'], 1)
        self.assertEqual(summary[1]['cantidad'], 1)
        self.assertEqual(summary[1]['importe_ars'], '85000.00')

    def test_summary_uses_sale_month(self):
        app.approve(self.rows, self.ledger, 0, True, '2026-10-01')
        self.assertEqual(app.monthly_summary(self.rows, self.ledger, '2026-09')[0]['importe_ars'], '85000.00')
        self.assertEqual(app.monthly_summary(self.rows, self.ledger, '2026-10')[0]['cantidad'], 0)


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.ledger = app.import_csv(app.EXAMPLE.encode(), {})

    def test_correct_duplicate_id_revalidates_both_rows(self):
        updated = app.correct_sale(self.rows, self.ledger, 2, {'id': 'V005'})
        checked = app.assess(updated, self.ledger)
        self.assertEqual([i['status'] for i in checked], ['pendiente'] * 4 + ['error'])
        self.assertEqual(self.rows[2]['id'], 'V003')
        self.assertEqual(app.monthly_summary(updated, self.ledger, '2026-09')[1]['importe_ars'], '310000.50')
        self.assertFalse(self.ledger)

    def test_correct_invalid_amount_with_decimal_comma(self):
        updated = app.correct_sale(self.rows, self.ledger, 4, {'importe': ' 17500,25 '})
        self.assertEqual(updated[4]['importe'], '17500.25')
        self.assertEqual(app.assess(updated, self.ledger)[4]['status'], 'pendiente')
        self.assertEqual(app.monthly_summary(updated, self.ledger, '2026-09')[1]['importe_ars'], '227500.75')

    def test_new_duplicate_id_rejected_without_mutation(self):
        original = copy.deepcopy(self.rows)
        with self.assertRaisesRegex(ValueError, 'otra venta'):
            app.correct_sale(self.rows, self.ledger, 0, {'id': 'V002'})
        self.assertEqual(self.rows, original)
        self.assertFalse(self.ledger)

    def test_processed_sale_cannot_change_even_its_id(self):
        app.approve(self.rows, self.ledger, 0, True)
        original, history = copy.deepcopy(self.rows), copy.deepcopy(self.ledger)
        for changes in [{'id': 'NUEVO'}, {'importe': '1'}, {'cliente': 'Otro'}]:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'no se puede editar'):
                app.correct_sale(self.rows, self.ledger, 0, changes)
        self.assertEqual(self.rows, original)
        self.assertEqual(self.ledger, history)

    def test_error_row_with_preserved_id_also_locked(self):
        app.approve(self.rows, self.ledger, 0, True)
        changed = copy.deepcopy(self.rows)
        changed[0]['importe'] = 'inválido'
        self.assertEqual(app.assess(changed, self.ledger)[0]['status'], 'error')
        with self.assertRaisesRegex(ValueError, 'no se puede editar'):
            app.correct_sale(changed, self.ledger, 0, {'id': 'V009', 'importe': '2'})

    def test_cannot_take_history_id_missing_from_current_csv(self):
        app.approve(self.rows, self.ledger, 0, True)
        remaining = self.rows[1:]
        with self.assertRaisesRegex(ValueError, 'comprobante conservado'):
            app.correct_sale(remaining, self.ledger, 0, {'id': 'V001'})

    def test_invalid_correction_is_atomic_and_revalidates_all_fields(self):
        original = copy.deepcopy(self.rows)
        for changes in [{'importe': 'NaN'}, {'fecha': '2026-02-30'}, {'email': 'real@otro.com'}, {'id': ' '}, {'estado': 'procesada'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                app.correct_sale(self.rows, self.ledger, 0, changes)
        self.assertEqual(self.rows, original)

    def test_corrections_survive_backup_without_changing_pdf_history(self):
        snap, _ = app.approve(self.rows, self.ledger, 0, True)
        old_pdf = app.build_pdf(snap)
        history = copy.deepcopy(self.ledger)
        corrected = app.correct_sale(self.rows, self.ledger, 2, {'id': 'V005'})
        corrected = app.correct_sale(corrected, self.ledger, 4, {'importe': '17500.25'})
        backup = app.export_registry(corrected, self.ledger)
        restored, ledger = app.import_csv(backup, {})
        self.assertEqual(self.ledger, history)
        self.assertEqual(ledger, history)
        self.assertEqual(app.build_pdf(ledger['V001']), old_pdf)
        self.assertEqual([r['status'] for r in app.assess(restored, ledger)], ['procesada'] + ['pendiente'] * 4)
        self.assertEqual(app.export_registry(restored, ledger), backup)
        self.assertFalse(app.approve(restored, ledger, 0, True)[1])

    def test_corrected_sale_still_requires_explicit_approval(self):
        updated = app.correct_sale(self.rows, self.ledger, 4, {'importe': '99.99'})
        with self.assertRaises(ValueError):
            app.approve(updated, self.ledger, 4, False)
        snap, created = app.approve(updated, self.ledger, 4, True)
        self.assertTrue(created)
        self.assertEqual(snap['importe'], '99.99')
        self.assertFalse(app.approve(updated, self.ledger, 4, True)[1])


class StreamlitTests(unittest.TestCase):
    def load(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()

    @staticmethod
    def button(at, label):
        return next(b for b in at.button if b.label == label)

    def test_ui_approval_rerun_and_reset(self):
        at = self.load()
        self.assertFalse(at.exception)
        self.button(at, 'Aprobar y generar comprobante demo').click().run()
        self.assertTrue(at.error)
        self.assertEqual(len(at.session_state['ledger']), 0)
        next(c for c in at.checkbox if c.label.startswith('Revisé')).check().run()
        self.button(at, 'Aprobar y generar comprobante demo').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state['ledger']), 1)
        at.run()
        self.assertEqual(len(at.session_state['ledger']), 1)
        downloads = [d.label for d in at.get('download_button')]
        self.assertIn('Descargar correo preparado', downloads)
        self.assertIn('Descargar PDF demo', downloads)
        self.assertTrue(self.button(at, 'Restablecer ejemplo').disabled)
        next(c for c in at.checkbox if c.label.startswith('Confirmo borrar')).check().run()
        self.button(at, 'Restablecer ejemplo').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state['ledger']), 0)
        self.assertEqual(len(at.session_state['rows']), 5)

    def test_ui_restored_registry(self):
        rows, ledger = app.import_csv(app.EXAMPLE.encode(), {})
        app.approve(rows, ledger, 0, True)
        rows, ledger = app.import_csv(app.export_registry(rows, ledger), {})
        at = self.load()
        at.session_state['rows'], at.session_state['ledger'] = rows, ledger
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state['ledger']), 1)
        self.assertIn('Descargar PDF demo', [d.label for d in at.get('download_button')])


    @staticmethod
    def input(at, label):
        return next(w for w in at.text_input if w.label == label)

    @staticmethod
    def select(at, label):
        return next(w for w in at.selectbox if w.label == label)

    def test_tabs_corrections_and_approval_flow(self):
        at = self.load()
        self.assertEqual([t.label for t in at.tabs], ['1 · Revisar', '2 · Preparar', '3 · Resumen'])
        self.assertEqual(self.select(at, 'Fila para corregir').value, 2)
        self.input(at, 'ID de venta').set_value('V005')
        self.button(at, 'Guardar corrección').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['rows'][2]['id'], 'V005')
        # The remaining invalid amount is selected automatically after revalidation.
        self.assertEqual(self.select(at, 'Fila para corregir').value, 4)
        self.input(at, 'Importe en pesos').set_value('17500,25')
        self.button(at, 'Guardar corrección').click().run()
        self.assertFalse(at.exception)
        self.assertFalse(any(i['errors'] for i in app.assess(at.session_state['rows'], at.session_state['ledger'])))
        self.select(at, 'Venta para revisar').select(2).run()
        next(c for c in at.checkbox if c.label.startswith('Revisé')).check().run()
        self.button(at, 'Aprobar y generar comprobante demo').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.session_state['ledger']), 1)
        self.assertIn('V005', at.session_state['ledger'])
        self.assertFalse(any(label.startswith('Fila 4 ·') for label in self.select(at, 'Fila para corregir').options))
        downloads = [d.label for d in at.get('download_button')]
        for label in ['Descargar PDF demo', 'Descargar correo preparado', 'Descargar registro actualizado CSV', 'Descargar resumen mensual CSV']:
            self.assertIn(label, downloads)
        at.run()
        self.assertEqual(len(at.session_state['ledger']), 1)

    def test_ui_rejects_duplicate_then_accepts_retry(self):
        at = self.load()
        before = copy.deepcopy(at.session_state['rows'])
        self.input(at, 'ID de venta').set_value('V001')
        self.button(at, 'Guardar corrección').click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)
        self.assertEqual(at.session_state['rows'], before)
        self.assertEqual(self.input(at, 'ID de venta').value, 'V001')
        self.input(at, 'ID de venta').set_value('V006')
        self.button(at, 'Guardar corrección').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['rows'][2]['id'], 'V006')

    def test_ui_excludes_conflicting_processed_id(self):
        at = self.load()
        rows, ledger = app.import_csv(app.EXAMPLE.encode(), {})
        app.approve(rows, ledger, 0, True)
        rows[0]['importe'] = 'importe incorrecto'
        at.session_state['rows'], at.session_state['ledger'] = rows, ledger
        at.run()
        self.assertFalse(at.exception)
        self.assertFalse(any(label.startswith('Fila 2 ·') for label in self.select(at, 'Fila para corregir').options))
        self.assertEqual(len(at.session_state['ledger']), 1)

    def test_ui_correction_clears_previous_approval(self):
        at = self.load()
        next(c for c in at.checkbox if c.label.startswith('Revisé')).check().run()
        self.input(at, 'ID de venta').set_value('V005')
        self.button(at, 'Guardar corrección').click().run()
        self.assertFalse(next(c for c in at.checkbox if c.label.startswith('Revisé')).value)
        self.assertEqual(len(at.session_state['ledger']), 0)


if __name__ == '__main__':
    unittest.main()
