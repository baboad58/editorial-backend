import { useState } from 'react'
import { Link } from 'react-router-dom'
import heroImg from '../assets/hero-library.jpg'

const STEPS = [
  {
    n: '01',
    title: 'Cuéntanos tu idea',
    text: 'Una frase, un párrafo o varias páginas. Cuanto más detalle, mejor. Tu idea es la semilla.',
  },
  {
    n: '02',
    title: 'Tu mayordomo la analiza',
    text: 'Un agente literario dedicado lee tu idea, te hace preguntas precisas y desentraña su potencial.',
  },
  {
    n: '03',
    title: 'Recibes un plan editorial',
    text: 'Tono, estructura, capítulos, portada. Un plan completo para que apruebes con una sola firma.',
  },
  {
    n: '04',
    title: 'Tu obra, entregada',
    text: 'Libro completo, editado y maquetado. Listo para leer, regalar o publicar.',
  },
]

export default function Landing() {
  return (
    <div className="min-h-screen bg-[#0a0a0f] text-stone-100 font-sans antialiased overflow-x-hidden">
      <Nav />
      <Hero />
      <Manifesto />
      <HowItWorks />
      <ContactCTA />
      <Footer />
    </div>
  )
}

/* ───────────────────────── NAV ───────────────────────── */
function Nav() {
  return (
    <header className="fixed top-0 inset-x-0 z-40 backdrop-blur-md bg-[#0a0a0f]/60 border-b border-white/5">
      <div className="max-w-7xl mx-auto px-6 lg:px-12 h-16 flex items-center justify-between">
        <a href="#" className="font-serif text-xl tracking-wide">
          O<span className="text-gold-500">b</span>ra
        </a>
        <nav className="hidden md:flex items-center gap-8 text-sm text-stone-400">
          <a href="#manifiesto" className="hover:text-stone-100 transition-colors">Manifiesto</a>
          <a href="#proceso"    className="hover:text-stone-100 transition-colors">Proceso</a>
          <a href="#contacto"   className="hover:text-stone-100 transition-colors">Contacto</a>
        </nav>
        <Link
          to="/acceso"
          className="text-xs tracking-widest uppercase border border-gold-500/40 text-gold-400
                     hover:bg-gold-500 hover:text-[#0a0a0f] transition-colors px-4 py-2 rounded-full"
        >
          Entrar al estudio
        </Link>
      </div>
    </header>
  )
}

/* ───────────────────────── HERO ───────────────────────── */
function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      {/* Background image */}
      <img
        src={heroImg}
        alt=""
        width={1920}
        height={1080}
        className="absolute inset-0 w-full h-full object-cover scale-105 animate-[heroZoom_20s_ease-in-out_infinite_alternate]"
      />
      {/* Overlays */}
      <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a0f]/60 via-[#0a0a0f]/40 to-[#0a0a0f]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_transparent_0%,_#0a0a0f_85%)]" />

      {/* Content */}
      <div className="relative z-10 max-w-5xl mx-auto px-6 text-center pt-20">
        <p className="text-xs md:text-sm tracking-[0.4em] uppercase text-gold-400/80 mb-8 animate-[fadeUp_1s_ease-out_0.2s_both]">
          Editorial · Inteligencia Artificial
        </p>

        <h1 className="font-serif text-5xl md:text-7xl lg:text-8xl leading-[1.05] tracking-tight animate-[fadeUp_1s_ease-out_0.4s_both]">
          Tú tienes la idea.<br />
          <span className="italic text-gold-400">Nosotros creamos</span><br />
          tu obra.
        </h1>

        <p className="mt-10 text-base md:text-lg text-stone-300 max-w-2xl mx-auto leading-relaxed animate-[fadeUp_1s_ease-out_0.7s_both]">
          Una editorial donde cada libro nace de una conversación. Tu idea, refinada por un mayordomo
          literario y materializada por nuestros agentes en una obra completa, editada y lista.
        </p>

        <div className="mt-12 flex flex-col sm:flex-row gap-4 justify-center items-center animate-[fadeUp_1s_ease-out_1s_both]">
          <Link
            to="/acceso"
            className="group relative inline-flex items-center gap-3 bg-gold-500 hover:bg-gold-400
                       text-[#0a0a0f] px-8 py-4 rounded-full font-medium tracking-wide
                       shadow-[0_10px_40px_-10px_rgba(212,168,87,0.6)] transition-all hover:scale-[1.02]"
          >
            Entrar con mi código
            <span className="transition-transform group-hover:translate-x-1">→</span>
          </Link>
          <a
            href="#proceso"
            className="text-sm text-stone-400 hover:text-stone-100 transition-colors px-6 py-4"
          >
            Ver el proceso
          </a>
        </div>
      </div>

      {/* Scroll indicator */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 text-stone-500 text-xs tracking-widest uppercase animate-bounce">
        ↓ Desliza
      </div>

      {/* Inline keyframes */}
      <style>{`
        @keyframes heroZoom { from { transform: scale(1.05) } to { transform: scale(1.15) } }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(24px) } to { opacity: 1; transform: translateY(0) } }
      `}</style>
    </section>
  )
}

/* ───────────────────────── MANIFIESTO ───────────────────────── */
function Manifesto() {
  return (
    <section id="manifiesto" className="relative py-32 px-6">
      <div className="max-w-3xl mx-auto text-center">
        <p className="text-xs tracking-[0.4em] uppercase text-gold-500/70 mb-8">Manifiesto</p>
        <p className="font-serif text-3xl md:text-5xl leading-[1.25] text-stone-200">
          Creemos que <span className="italic text-gold-400">toda idea</span> merece convertirse
          en libro. No la tuya menos.
        </p>
        <div className="mt-12 mx-auto h-px w-24 bg-gold-500/40" />
        <p className="mt-12 text-stone-400 leading-relaxed">
          Llevas años con esa historia. Ese ensayo. Esa guía. La idea está. Lo que falta es el
          tiempo, el oficio, el equipo. Eso es lo que somos: cinco agentes literarios trabajando
          en silencio para que tu obra exista.
        </p>
      </div>
    </section>
  )
}

/* ───────────────────────── PROCESO ───────────────────────── */
function HowItWorks() {
  return (
    <section id="proceso" className="relative py-32 px-6 bg-gradient-to-b from-transparent via-[#11111a] to-transparent">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-20">
          <p className="text-xs tracking-[0.4em] uppercase text-gold-500/70 mb-6">El proceso</p>
          <h2 className="font-serif text-4xl md:text-6xl leading-tight">
            De la idea al libro,<br />
            <span className="italic text-gold-400">en cuatro actos.</span>
          </h2>
        </div>

        <div className="grid md:grid-cols-2 gap-px bg-white/5 rounded-2xl overflow-hidden border border-white/5">
          {STEPS.map(s => (
            <article
              key={s.n}
              className="group bg-[#0a0a0f] p-10 md:p-14 hover:bg-[#11111a] transition-colors"
            >
              <div className="flex items-baseline gap-6 mb-6">
                <span className="font-serif text-5xl text-gold-500/40 group-hover:text-gold-500 transition-colors">
                  {s.n}
                </span>
                <h3 className="font-serif text-2xl md:text-3xl text-stone-100">{s.title}</h3>
              </div>
              <p className="text-stone-400 leading-relaxed pl-[4.5rem]">{s.text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ───────────────────────── CONTACTO ───────────────────────── */
function ContactCTA() {
  const [form, setForm] = useState({ name: '', email: '', idea: '' })
  const [errors, setErrors] = useState({})
  const [sent, setSent] = useState(false)

  const validate = () => {
    const e = {}
    const name = form.name.trim()
    const email = form.email.trim()
    const idea = form.idea.trim()
    if (!name || name.length > 100) e.name = 'Nombre requerido (máx. 100)'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 255) e.email = 'Email no válido'
    if (idea.length < 20 || idea.length > 4000) e.idea = 'Cuéntanos entre 20 y 4000 caracteres'
    return e
  }

  const handleSubmit = (ev) => {
    ev.preventDefault()
    const e = validate()
    setErrors(e)
    if (Object.keys(e).length) return

    const subject = encodeURIComponent(`Nueva idea de ${form.name.trim()}`)
    const body = encodeURIComponent(
      `Nombre: ${form.name.trim()}\nEmail: ${form.email.trim()}\n\nIdea:\n${form.idea.trim()}`
    )
    window.location.href = `mailto:hola@obra.editorial?subject=${subject}&body=${body}`
    setSent(true)
  }

  return (
    <section id="contacto" className="relative py-32 px-6">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-14">
          <p className="text-xs tracking-[0.4em] uppercase text-gold-500/70 mb-6">Solicita tu invitación</p>
          <h2 className="font-serif text-4xl md:text-6xl leading-tight">
            Confía tu idea.<br />
            <span className="italic text-gold-400">Te enviamos tu código.</span>
          </h2>
          <p className="mt-6 text-sm text-stone-400 max-w-xl mx-auto">
            El estudio está en beta cerrada. Cuéntanos tu idea y te enviaremos un código de invitación
            en menos de 24h. ¿Ya tienes uno?{' '}
            <Link to="/acceso" className="text-gold-400 hover:text-gold-300 underline underline-offset-4">
              Entra al estudio
            </Link>.
          </p>
        </div>

        {sent ? (
          <div className="text-center border border-gold-500/30 rounded-2xl p-12 bg-gold-500/5">
            <p className="font-serif text-3xl text-gold-400 mb-3">Gracias.</p>
            <p className="text-stone-400">Hemos abierto tu cliente de correo. Tu idea está a un envío de distancia.</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid md:grid-cols-2 gap-6">
              <Field label="Tu nombre" error={errors.name}>
                <input
                  type="text"
                  maxLength={100}
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-transparent border-0 border-b border-white/20 focus:border-gold-500
                             outline-none py-3 text-stone-100 placeholder-stone-600 transition-colors"
                  placeholder="María García"
                />
              </Field>
              <Field label="Email" error={errors.email}>
                <input
                  type="email"
                  maxLength={255}
                  value={form.email}
                  onChange={e => setForm({ ...form, email: e.target.value })}
                  className="w-full bg-transparent border-0 border-b border-white/20 focus:border-gold-500
                             outline-none py-3 text-stone-100 placeholder-stone-600 transition-colors"
                  placeholder="maria@ejemplo.com"
                />
              </Field>
            </div>

            <Field label="Tu idea — cuanto más detalle, mejor" error={errors.idea}>
              <textarea
                rows={6}
                maxLength={4000}
                value={form.idea}
                onChange={e => setForm({ ...form, idea: e.target.value })}
                className="w-full bg-transparent border border-white/10 focus:border-gold-500 rounded-xl
                           outline-none p-4 text-stone-100 placeholder-stone-600 resize-none transition-colors"
                placeholder="El protagonista es… El libro trata sobre… Quiero que el tono sea…"
              />
              <p className="text-xs text-stone-600 mt-2 text-right">{form.idea.length} / 4000</p>
            </Field>

            <div className="pt-4 flex justify-center">
              <button
                type="submit"
                className="group inline-flex items-center gap-3 bg-gold-500 hover:bg-gold-400
                           text-[#0a0a0f] px-10 py-4 rounded-full font-medium tracking-wide
                           shadow-[0_10px_40px_-10px_rgba(212,168,87,0.6)] transition-all hover:scale-[1.02]"
              >
                Enviar mi idea
                <span className="transition-transform group-hover:translate-x-1">→</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  )
}

function Field({ label, error, children }) {
  return (
    <label className="block">
      <span className="block text-xs tracking-[0.2em] uppercase text-stone-500 mb-2">{label}</span>
      {children}
      {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
    </label>
  )
}

/* ───────────────────────── FOOTER ───────────────────────── */
function Footer() {
  return (
    <footer className="border-t border-white/5 py-12 px-6 text-center">
      <p className="font-serif text-2xl mb-3">O<span className="text-gold-500">b</span>ra</p>
      <p className="text-xs text-stone-600 tracking-wider uppercase">
        Editorial de obras creadas con IA · {new Date().getFullYear()}
      </p>
    </footer>
  )
}
