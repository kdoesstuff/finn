import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { NetworkReply } from '../api/types'
import { ContractError, parseDigest } from '../api/validate'
import { parseNetworkReply, parseWhoToCall } from './api'
import type { AppConfig } from '../config'
import { fakeApi, json } from '../test/fakeServer'
import { liveDigest, session } from '../test/fixtures/contract'
import { NETWORK_BUILD } from './flag'
import { NetworkScreen } from './NetworkScreen'
import { WhoToCall } from './WhoToCall'

const config: AppConfig = { apiUrl: 'https://api.finn.test', networkEnabled: true, sentryDsn: null }
const CAUTION = 'Works there now: ask about what is already public, never about unpublished price-sensitive information.'

const answer = {
  person_id: 'p061',
  name: 'Pranav Seshadri',
  headline: 'Plant Head, Tata Power',
  degree: 1,
  why: 'Plant Head at Tata Power since 2019: knows how projects and capacity are run there.',
  how: 'Classmate, IIM Ahmedabad (PGP 2010) (tie strength 5 of 5)',
  via: null,
  caution: CAUTION,
  path: [{ from: 'you', to: 'Pranav Seshadri', to_id: 'p061', kind: 'classmate', strength: 5, context: 'Classmate' }],
}
const second = { ...answer, person_id: 'p120', name: 'Ira Wagle', degree: 2, via: 'Kabir Ekbote', caution: null }
const reply: NetworkReply = {
  question: 'Who worked at Tata Power?',
  kind: 'company',
  title: 'People who can explain Tata Power',
  answers: [answer, second],
  company: {
    symbol: 'TATAPOWER',
    company: 'Tata Power',
    sector: 'power',
    synthetic: true,
    you_worked_there: [],
    worked_there: [answer],
    best_placed: [answer, second],
  },
}
const person = {
  id: 'p061',
  name: 'Pranav Seshadri',
  headline: 'Plant Head, Tata Power',
  location: 'Pune',
  degree: 1,
  synthetic: true,
  career: ['Production Engineer, Tata Power (2010-2015)', 'Plant Head, Tata Power (since 2015)'],
  schools: ['IIM Ahmedabad, PGP (2010)'],
  how: 'Classmate, IIM Ahmedabad (PGP 2010) (tie strength 5 of 5)',
  path: answer.path,
  overlaps: ['IIM Ahmedabad, same year (2010)'],
  what_to_ask: ["How Tata Power's operations side works (now), and what changed after they joined."],
}

describe('network contract', () => {
  it('checks who_to_call entries, and the core build (as here) does not read them at all', () => {
    const entry = { person_id: 'p061', name: 'X Y', why: 'W.', degree: 1, via: null, caution: null }
    expect(parseWhoToCall(entry, 'w')).toEqual(entry)
    expect(() => parseWhoToCall({ ...entry, degree: 3 }, 'w')).toThrow(ContractError)
    const full = structuredClone(liveDigest) as unknown as { attention: Record<string, unknown>[] }
    full.attention[0]!.who_to_call = [entry]
    expect(parseDigest(full).attention[0]!.who_to_call).toBeUndefined()
  })

  it('refuses a reply of an unknown kind', () => {
    expect(parseNetworkReply(reply).answers).toHaveLength(2)
    expect(() => parseNetworkReply({ ...reply, kind: 'gossip' })).toThrow(/reply.kind/)
  })

  it('is off in the test build, as in the core build', () => {
    expect(NETWORK_BUILD).toBe(false)
  })
})

describe('NetworkScreen', () => {
  function renderScreen(routes: Parameters<typeof fakeApi>[0], path = '/network') {
    window.history.replaceState(null, '', path)
    const { api, server } = fakeApi({ 'POST /v1/session/demo': json(session), ...routes })
    render(<NetworkScreen api={api} config={config} navigate={() => undefined} focusHeading={false} />)
    return { server, user: userEvent.setup() }
  }

  it('asks the question in the address, shows each person with the reason and the path', async () => {
    const { server } = renderScreen({ 'GET /v1/network/ask': json(reply) }, '/network?q=Who%20worked%20at%20Tata%20Power%3F')
    const heading = await screen.findByRole('heading', { name: /People who can explain Tata Power/ })
    expect(heading).toBeTruthy()
    expect(server.callsTo('GET /v1/network/ask')[0]!.url.searchParams.get('q')).toBe('Who worked at Tata Power?')
    expect(server.callsTo('GET /v1/network/ask')[0]!.headers.get('authorization')).toMatch(/^Bearer /)
    const people = screen.getAllByRole('listitem').filter((li) => li.classList.contains('net-person'))
    expect(within(people[0]!).getByText(/knows how projects and capacity are run there/)).toBeTruthy()
    expect(within(people[0]!).getByText(CAUTION)).toBeTruthy()
    expect(within(people[1]!).getByText(/Through Kabir Ekbote/)).toBeTruthy()
  })

  it('opens a person for diligence and comes back to the answers', async () => {
    const { user } = renderScreen({ 'GET /v1/network/ask': json(reply), 'GET /v1/network/person/p061': json(person) })
    await user.click(screen.getByRole('button', { name: 'Who worked at Tata Power?' }))
    await user.click((await screen.findAllByRole('button', { name: 'Pranav Seshadri' }))[0]!)
    expect(await screen.findByRole('heading', { name: 'What to ask' })).toBeTruthy()
    expect(screen.getByText('IIM Ahmedabad, same year (2010)')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Back to the answers' }))
    expect(await screen.findByRole('heading', { name: /People who can explain Tata Power/ })).toBeTruthy()
  })

  it('says plainly when this edition has no network', async () => {
    const { user } = renderScreen({
      'GET /v1/network/ask': json({ error: { code: 'not_found', message: 'There is no such route.' } }, 404),
    })
    await user.type(screen.getByRole('searchbox', { name: 'Ask your network' }), 'Who knows banking?')
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText('Network is not part of this edition of FINN.')).toBeTruthy()
  })
})

describe('WhoToCall', () => {
  it('lists who can explain an item behind a disclosure, with the caution for current employees', async () => {
    const user = userEvent.setup()
    render(
      <WhoToCall
        company="Tata Power"
        people={[
          { person_id: 'p061', name: 'Pranav Seshadri', why: answer.why, degree: 1, via: null, caution: CAUTION },
          { person_id: 'p120', name: 'Ira Wagle', why: 'Was at Tata Power.', degree: 2, via: 'Kabir Ekbote', caution: null },
        ]}
      />,
    )
    const toggle = screen.getByRole('button', { name: 'Who in your network can explain this (2)' })
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    await user.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('Through Kabir Ekbote')).toBeTruthy()
    expect(screen.getByText(CAUTION)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Ask your network' }).getAttribute('href')).toBe(
      '/network?q=Who%20can%20explain%20Tata%20Power%3F',
    )
  })

  it('renders nothing for an empty list', () => {
    const { container } = render(<WhoToCall company="X" people={[]} />)
    expect(container.innerHTML).toBe('')
  })
})
