import { Link } from 'react-router-dom'
import { useEffect } from 'react'

export default function Terms() {
  useEffect(() => {
    document.title = 'Términos de Servicio · Obra'
    window.scrollTo(0, 0)
  }, [])

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-stone-100 font-sans antialiased">
      {/* Nav */}
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
          Términos de <span className="italic text-gold-400">Servicio</span>
        </h1>
        <p className="text-sm text-stone-500 mb-16">
          Última actualización: {new Date().toLocaleDateString('es-ES', { year: 'numeric', month: 'long', day: 'numeric' })}
        </p>

        <div className="space-y-12 text-stone-300 leading-relaxed">
          <Section n="01" title="Aceptación de los términos">
            <p>
              Al acceder o utilizar Obra (el “Servicio”), confirmas que has leído, comprendido y
              aceptado estos Términos de Servicio. Si no estás de acuerdo con alguno de ellos,
              te pedimos que no utilices el Servicio.
            </p>
          </Section>

          <Section n="02" title="Descripción del servicio">
            <p>
              Obra es una editorial que utiliza herramientas de Inteligencia Artificial para
              asistir en la creación de obras literarias a partir de las ideas aportadas por
              cada usuario. El acceso al estudio se realiza mediante código de invitación.
            </p>
          </Section>

          <Section n="03" title="Obras generadas con IA y derechos de autor">
            <p>
              Todas las obras producidas a través de Obra son creadas con la asistencia
              sustancial de sistemas de Inteligencia Artificial generativa. Conforme a los
              criterios actuales en numerosas jurisdicciones —incluida la doctrina de la U.S.
              Copyright Office— las obras generadas predominantemente por IA{' '}
              <span className="text-gold-400">no están sujetas a derechos de autor</span> y se
              consideran de <span className="text-gold-400">dominio público</span>.
            </p>
            <p>
              Esto significa que cualquier persona puede leer, copiar, distribuir, modificar
              o utilizar comercialmente las obras producidas, sin necesidad de permiso ni
              pago de regalías.
            </p>
          </Section>

          <Section n="04" title="Tu contenido">
            <p>
              Las ideas, descripciones y materiales de referencia que aportas siguen siendo
              tuyos. Nos otorgas una licencia limitada y no exclusiva para procesarlos con
              el único fin de generar la obra que solicitas.
            </p>
          </Section>

          <Section n="05" title="Uso aceptable">
            <p>
              No está permitido utilizar el Servicio para generar contenido ilegal, difamatorio,
              que infrinja derechos de terceros, que promueva el odio o que ponga en riesgo
              la integridad de menores. Nos reservamos el derecho de suspender el acceso ante
              cualquier uso indebido.
            </p>
          </Section>

          <Section n="06" title="Disponibilidad y limitación de responsabilidad">
            <p>
              El Servicio se ofrece “tal cual”. No garantizamos disponibilidad ininterrumpida
              ni la idoneidad de las obras generadas para un propósito particular. En la
              máxima medida permitida por la ley, Obra no será responsable de daños indirectos
              derivados del uso del Servicio.
            </p>
          </Section>

          <Section n="07" title="Modificaciones">
            <p>
              Podemos actualizar estos Términos en cualquier momento. La versión vigente
              estará siempre publicada en esta página, con su fecha de actualización.
            </p>
          </Section>

          <Section n="08" title="Contacto">
            <p>
              Para cualquier consulta sobre estos Términos, escríbenos a{' '}
              <a href="mailto:cmachuc@gmail.com" className="text-gold-400 hover:text-gold-300 underline underline-offset-4">
                cmachuc@gmail.com
              </a>.
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
