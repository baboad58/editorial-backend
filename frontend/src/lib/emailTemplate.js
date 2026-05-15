// Mirror del builder de correo (supabase/functions/_shared/email.ts) para vista previa en la consola.
// Mantener sincronizado con el archivo del backend.

export const ASSIGNMENT_FROM = 'Editorial OBRA <onboarding@resend.dev>'
export const ASSIGNMENT_SUBJECT = 'Solicitud de código acceso a OBRA'

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function buildAssignmentEmail({ name, code, email }) {
  const safeName = escapeHtml(name)
  const safeCode = escapeHtml(code)
  const safeEmail = escapeHtml(email)

  const text = `Felicitaciones ${name},

Te entrego el código ${code} para que puedas ingresar al portal con tu correo ${email}.

Adelante con tu obra.

Te saluda atentamente,
Alfred`

  const html = `<!doctype html>
<html lang="es">
  <body style="margin:0;padding:24px;background:#f5f5f4;font-family:Helvetica,Arial,sans-serif;color:#1c1917;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #e7e5e4;border-radius:12px;">
      <tr><td style="padding:28px 28px 8px;">
        <p style="font-size:12px;letter-spacing:0.2em;text-transform:uppercase;color:#a8a29e;margin:0 0 8px;">Editorial OBRA</p>
        <h1 style="font-family:Georgia,serif;font-size:22px;margin:0 0 16px;color:#0c0a09;">Felicitaciones ${safeName}</h1>
        <p style="font-size:15px;line-height:1.55;margin:0 0 16px;">
          Te entrego el código de acceso para que puedas ingresar al portal con tu correo
          <strong>${safeEmail}</strong>.
        </p>
        <p style="margin:24px 0;text-align:center;">
          <span style="display:inline-block;padding:14px 22px;font-family:'Courier New',monospace;font-size:20px;letter-spacing:0.18em;background:#fafaf9;border:1px solid #d6d3d1;border-radius:8px;color:#0c0a09;">${safeCode}</span>
        </p>
        <p style="font-size:15px;line-height:1.55;margin:0 0 24px;">Adelante con tu obra.</p>
        <p style="font-size:14px;color:#57534e;margin:0;">Te saluda atentamente,<br/><strong>Alfred</strong></p>
      </td></tr>
    </table>
  </body>
</html>`

  return { from: ASSIGNMENT_FROM, subject: ASSIGNMENT_SUBJECT, text, html }
}
