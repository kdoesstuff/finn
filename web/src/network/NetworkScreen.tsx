import { type SyntheticEvent, useEffect, useId, useRef, useState } from 'react'
import { ApiError, type Api } from '../api/client'
import type { NetworkAnswer, NetworkPerson, NetworkReply } from '../api/types'
import type { AppConfig } from '../config'
import { askNetwork, networkPerson } from './api'
import { Colophon, Wordmark } from '../screens/Chrome'
import './network.css'

const EXAMPLES = [
  'Who worked at Tata Power?',
  'Who can explain Navin Fluorine’s new plant?',
  'Who knows auto components?',
  'Who should I reconnect with?',
  'Who knows legal and compliance in banking?',
]

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'reply'; reply: NetworkReply }
  | { kind: 'person'; person: NetworkPerson; back: NetworkReply | null }
  | { kind: 'error'; message: string }

interface Props {
  api: Api
  config: AppConfig
  navigate: (to: string) => void
  focusHeading: boolean
}

function messageFor(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) return 'Network is not part of this edition of FINN.'
  if (error instanceof ApiError && error.status === 429) return 'Too many questions in a minute. Try again shortly.'
  return 'FINN could not answer just now. Try again in a moment.'
}

function stateFor(reply: NetworkReply): State {
  return reply.kind === 'person' && reply.person
    ? { kind: 'person', person: reply.person, back: null }
    : { kind: 'reply', reply }
}

/** The full edition's "ask your network" screen: a question in, the people and the reasons out. */
export function NetworkScreen({ api, config, navigate, focusHeading }: Props) {
  const [initial] = useState(() => (new URLSearchParams(window.location.search).get('q') ?? '').trim())
  const [q, setQ] = useState(initial)
  const [state, setState] = useState<State>(initial === '' ? { kind: 'idle' } : { kind: 'loading' })
  const heading = useRef<HTMLHeadingElement>(null)
  const inputId = useId()
  const pending = useRef<AbortController | null>(null)

  useEffect(() => {
    if (focusHeading) heading.current?.focus()
  }, [focusHeading])

  /** Asks, and sets state only once the answer (or the failure) is in. */
  async function fetchReply(text: string): Promise<void> {
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    try {
      const reply = await askNetwork(api, text, { signal: controller.signal })
      setState(stateFor(reply))
    } catch (error) {
      if (!controller.signal.aborted) setState({ kind: 'error', message: messageFor(error) })
    }
  }

  function ask(question: string) {
    const text = question.trim()
    if (text === '') return
    window.history.replaceState(window.history.state, '', `/network?q=${encodeURIComponent(text)}`)
    setState({ kind: 'loading' })
    void fetchReply(text)
  }

  async function openPerson(id: string, back: NetworkReply | null) {
    setState({ kind: 'loading' })
    try {
      const person = await networkPerson(api, id)
      setState({ kind: 'person', person, back })
    } catch (error) {
      setState({ kind: 'error', message: messageFor(error) })
    }
  }

  // The question in the address, once, when the screen opens; later questions come from the form.
  useEffect(() => {
    if (initial === '') return
    const controller = new AbortController()
    pending.current = controller
    askNetwork(api, initial, { signal: controller.signal }).then(
      (reply) => {
        if (!controller.signal.aborted) setState(stateFor(reply))
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setState({ kind: 'error', message: messageFor(error) })
      },
    )
    return () => controller.abort()
  }, [api, initial])

  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()
    ask(q)
  }

  const backTo = (back: NetworkReply | null) => (back ? () => setState({ kind: 'reply', reply: back }) : null)

  return (
    <div className="page page--network">
      <header className="masthead">
        <div className="masthead__brand">
          <Wordmark onHome={() => navigate('/')} />
          <span className="tag">Synthetic network</span>
        </div>
        <h1 className="masthead__date" tabIndex={-1} ref={heading}>
          Your network
        </h1>
        <p className="net-lede">
          Who to call, and why: people you know, or can reach through someone you know, at the companies you hold.
        </p>
        <p className="net-back">
          <a
            href="/brief"
            onClick={(event) => {
              event.preventDefault()
              navigate('/brief')
            }}
          >
            Back to your brief
          </a>
        </p>
      </header>
      <main className="net" aria-busy={state.kind === 'loading'}>
        <form className="net-ask" onSubmit={submit} role="search">
          <label htmlFor={inputId} className="net-ask__label">
            Ask your network
          </label>
          <div className="net-ask__row">
            <input
              id={inputId}
              className="net-ask__input"
              type="search"
              value={q}
              maxLength={200}
              placeholder="A company, a person, a sector"
              onChange={(event) => setQ(event.target.value)}
            />
            <button type="submit" className="button button--primary">
              Ask
            </button>
          </div>
          <ul className="net-chips" aria-label="Questions to try">
            {EXAMPLES.map((example) => (
              <li key={example}>
                <button
                  type="button"
                  className="net-chip"
                  onClick={() => {
                    setQ(example)
                    ask(example)
                  }}
                >
                  {example}
                </button>
              </li>
            ))}
          </ul>
        </form>
        <div aria-live="polite">
          {state.kind === 'loading' && <p className="net-status">Asking your network…</p>}
          {state.kind === 'error' && <p className="net-status net-status--error">{state.message}</p>}
          {state.kind === 'reply' && (
            <Reply
              reply={state.reply}
              onPerson={(id) => void openPerson(id, state.reply)}
              onAsk={(text) => {
                setQ(text)
                ask(text)
              }}
            />
          )}
          {state.kind === 'person' && <PersonView person={state.person} onBack={backTo(state.back)} />}
        </div>
      </main>
      <Colophon networkEnabled={config.networkEnabled} onHome={() => navigate('/')} />
    </div>
  )
}

function Reply({ reply, onPerson, onAsk }: { reply: NetworkReply; onPerson: (id: string) => void; onAsk: (q: string) => void }) {
  if (reply.kind === 'help') {
    return (
      <section className="net-reply" aria-labelledby="net-reply-title">
        <h2 className="section__title" id="net-reply-title">{reply.title}</h2>
        <ul className="net-chips">
          {(reply.examples ?? []).map((example) => (
            <li key={example}>
              <button type="button" className="net-chip" onClick={() => onAsk(example)}>
                {example}
              </button>
            </li>
          ))}
        </ul>
      </section>
    )
  }
  const company = reply.company
  return (
    <section className="net-reply" aria-labelledby="net-reply-title">
      <h2 className="section__title" id="net-reply-title">
        {reply.title} <span className="section__count">{reply.answers.length}</span>
      </h2>
      {company && company.you_worked_there.length > 0 && (
        <p className="note">You worked there: {company.you_worked_there.join('; ')}.</p>
      )}
      {reply.answers.length === 0 ? (
        <p className="net-status">Nobody in your network matches that yet.</p>
      ) : (
        <ol className="net-people">
          {reply.answers.map((a) => (
            <AnswerEntry key={a.person_id} answer={a} onPerson={onPerson} />
          ))}
        </ol>
      )}
      {company && company.worked_there.length > 0 && (
        <details className="net-more">
          <summary>Everyone who worked at {company.company} ({company.worked_there.length})</summary>
          <ol className="net-people">
            {company.worked_there.map((a) => (
              <AnswerEntry key={a.person_id} answer={a} onPerson={onPerson} />
            ))}
          </ol>
        </details>
      )}
    </section>
  )
}

function AnswerEntry({ answer, onPerson }: { answer: NetworkAnswer; onPerson: (id: string) => void }) {
  return (
    <li className="net-person">
      <p className="net-person__name">
        <button type="button" className="net-person__open" onClick={() => onPerson(answer.person_id)}>
          {answer.name}
        </button>
        <span className="net-person__degree">{answer.degree === 1 ? 'Your contact' : 'Second degree'}</span>
      </p>
      <p className="net-person__headline">{answer.headline}</p>
      <p className="net-person__why">{answer.why}</p>
      <p className="net-person__how">{answer.via ? `Through ${answer.via}. ` : ''}{answer.how}</p>
      {answer.caution && <p className="note">{answer.caution}</p>}
    </li>
  )
}

function PersonView({ person, onBack }: { person: NetworkPerson; onBack: (() => void) | null }) {
  return (
    <article className="net-reply net-profile" aria-labelledby="net-person-name">
      {onBack && (
        <button type="button" className="action" onClick={onBack}>
          Back to the answers
        </button>
      )}
      <h2 className="section__title" id="net-person-name">
        {person.name}
      </h2>
      <p className="net-person__headline">
        {person.headline}
        {person.location ? `, ${person.location}` : ''}
        {person.synthetic ? ' (synthetic)' : ''}
      </p>
      <h3 className="net-profile__h">How you reach them</h3>
      <ol className="net-path">
        {person.path.map((s, i) => (
          <li key={i}>
            {s.from} → {s.to}: {s.context} (strength {s.strength} of 5)
          </li>
        ))}
      </ol>
      {person.overlaps.length > 0 && (
        <>
          <h3 className="net-profile__h">Where your paths crossed</h3>
          <ul className="net-list">{person.overlaps.map((o) => <li key={o}>{o}</li>)}</ul>
        </>
      )}
      <h3 className="net-profile__h">Career</h3>
      <ul className="net-list">{person.career.map((c) => <li key={c}>{c}</li>)}</ul>
      {person.schools.length > 0 && (
        <>
          <h3 className="net-profile__h">Education</h3>
          <ul className="net-list">{person.schools.map((s) => <li key={s}>{s}</li>)}</ul>
        </>
      )}
      <h3 className="net-profile__h">What to ask</h3>
      <ul className="net-list">{person.what_to_ask.map((w) => <li key={w}>{w}</li>)}</ul>
    </article>
  )
}
