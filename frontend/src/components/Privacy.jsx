import { Link } from 'react-router-dom'
import { useEffect } from 'react'

export default function Privacy() {
  useEffect(() => {
    document.title = 'Política de Privacidad · Obra'
    window.scrollTo(0, 0)
  }, [])

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-stone-100 font-sans antialiased">
      <header className="fixed top-0 inset-x-0 z-40 backdrop-blur-md bg-[#0a0a0f]/60 border-b border-white/5">
        <div className="max-w-7xl mx-auto px-6 lg:px-12 h-16 flex items-center justify-between">
          <Link to="/" className="font-serif text-xl tracking-wide">
            O<span className="text-gold-500">b</span>ra
          </Link>
          <Link
            to="/"
            className="text-xs tracking-widest uppercase text-stone-400 hover:text-stone-100 transition-colors"
          >
            ← Volver
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 pt-32 pb-24">
        <p className="text-xs tracking-[0.4em] uppercase text-gold-500/70 mb-6">Legal</p>
        <h1 className="font-serif text-4xl md:text-6xl leading-tight mb-4">
          Política de <span className="italic text-gold-400">Privacidad</span>
        </h1>
        <p className="text-sm text-stone-500 mb-16">
          Última actualización: {new Date().toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' })}
        </p>

        <div className="space-y-12 text-stone-300 leading-relaxed">
          <Section n="01" title="Quiénes somos">
            <p>
              Obra es una editorial que utiliza herramientas de Inteligencia Artificial para
              asistir en la creación de obras literarias. El responsable del tratamiento de
              tus datos es el equipo de Obra, contacto:{' '}
              <a href="mailto:cmachuc@gmail.com" className="text-gold-400 hover:text-gold-300 underline underline-offset-4">
                cmachuc@gmail.com
              </a>.
            </p>
          </Section>

          <Section n="02" title="Datos que recogemos">
            <p>Tratamos únicamente los datos estrictamente necesarios para prestar el servicio:</p>
            <ul className="list-disc pl-5 space-y-2 marker:text-gold-500/60">
              <li><span className="text-stone-200">Datos de contacto:</span> nombre y correo electrónico que nos facilitas en el formulario de invitación.</li>
              <li><span className="text-stone-200">Tu idea / contenido:</span> el texto que envías para que sea procesado por nuestros agentes de IA.</li>
              <li><span className="text-stone-200">Código de invitación:</span> almacenado localmente en tu navegador para mantener tu sesión.</li>
              <li><span className="text-stone-200">Datos técnicos mínimos:</span> registros de uso del estudio (errores, latencia) sin identificadores personales.</li>
            </ul>
            <p>No utilizamos cookies de seguimiento ni herramientas de publicidad.</p>
          </Section>

          <Section n="03" title="Para qué usamos tus datos">
            <ul className="list-disc pl-5 space-y-2 marker:text-gold-500/60">
              <li>Responder a tu solicitud de invitación y enviarte el código de acceso.</li>
              <li>Procesar tu idea para generar la obra solicitada.</li>
              <li>Mantener la seguridad y el correcto funcionamiento del servicio.</li>
              <li>Cumplir con obligaciones legales aplicables.</li>
            </ul>
            <p>
              No vendemos, alquilamos ni cedemos tus datos a terceros con fines comerciales.
            </p>
          </Section>

          <Section n="04" title="Base legal">
            <p>
              El tratamiento se basa en tu <span className="text-stone-200">consentimiento</span>{' '}
              al enviar el formulario y en la <span className="text-stone-200">ejecución del
              servicio solicitado</span>. Puedes retirar tu consentimiento en cualquier momento
              escribiéndonos.
            </p>
          </Section>

          <Section n="05" title="Encargados del tratamiento">
            <p>
              Para generar las obras utilizamos proveedores de modelos de Inteligencia Artificial
              (por ejemplo, OpenAI, Anthropic u otros equivalentes) como encargados del
              tratamiento. Tu idea se transmite a estos proveedores únicamente con el fin de
              generar tu libro, bajo sus respectivos compromisos de confidencialidad y no
              reentrenamiento sobre datos de cliente.
            </p>
          </Section>

          <Section n="06" title="Conservación">
            <p>
              Conservamos tus datos mientras exista una relación activa contigo y, posteriormente,
              durante el plazo legalmente exigible. Las obras generadas pueden conservarse de
              forma anonimizada con fines de mejora del servicio.
            </p>
          </Section>

          <Section n="07" title="Tus derechos">
            <p>De acuerdo con el RGPD y la normativa aplicable, puedes ejercer en cualquier momento los derechos de:</p>
            <ul className="list-disc pl-5 space-y-2 marker:text-gold-500/60">
              <li>Acceso, rectificación y supresión de tus datos.</li>
              <li>Oposición y limitación del tratamiento.</li>
              <li>Portabilidad de tus datos.</li>
              <li>Retirar tu consentimiento.</li>
              <li>Presentar reclamación ante la autoridad de control competente.</li>
            </ul>
            <p>
              Para ejercerlos, escríbenos a{' '}
              <a href="mailto:cmachuc@gmail.com" className="text-gold-400 hover:text-gold-300 underline underline-offset-4">
                cmachuc@gmail.com
              </a>.
            </p>
          </Section>

          <Section n="08" title="Seguridad">
            <p>
              Aplicamos medidas técnicas y organizativas razonables para proteger tus datos
              frente a accesos no autorizados, pérdida o alteración. Las comunicaciones se
              realizan siempre sobre conexiones cifradas (HTTPS).
            </p>
          </Section>

          <Section n="09" title="Cambios en esta política">
            <p>
              Podemos actualizar esta política para reflejar cambios legales o del servicio.
              La versión vigente estará siempre publicada en esta página, indicando su fecha
              de actualización.
            </p>
          </Section>
        </div>

        <div className="mt-20 pt-10 border-t border-white/10 text-center">
          <Link
            to="/"
            className="text-xs tracking-widest uppercase text-stone-500 hover:text-gold-400 transition-colors"
          >
            ← Volver a la portada
          </Link>
        </div>
      </main>
    </div>
  )
}

function Section({ n, title, children }) {
  return (
    <section>
      <div className="flex items-baseline gap-5 mb-4">
        <span className="font-serif text-2xl text-gold-500/50">{n}</span>
        <h2 className="font-serif text-2xl md:text-3xl text-stone-100">{title}</h2>
      </div>
      <div className="pl-[3.25rem] space-y-4 text-stone-400">{children}</div>
    </section>
  )
}
