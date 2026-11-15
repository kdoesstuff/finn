// The full edition's Network calls and their checks (docs/API.md, "Network"). Imported only by
// network components, so none of it is in the core build.

import type { Api, CallOptions } from '../api/client'
import type { NetworkAnswer, NetworkCompany, NetworkKind, NetworkPerson, NetworkReply, NetworkStep, WhoToCall } from '../api/types'
import { arr, bool, ContractError, int, obj, str } from '../api/validate'

export function askNetwork(api: Api, q: string, options: CallOptions = {}): Promise<NetworkReply> {
  return api.get(`/v1/network/ask?q=${encodeURIComponent(q)}`, parseNetworkReply, options)
}

export function networkPerson(api: Api, id: string, options: CallOptions = {}): Promise<NetworkPerson> {
  return api.get(`/v1/network/person/${encodeURIComponent(id)}`, parseNetworkPerson, options)
}

function optStr(value: unknown, path: string): string | null {
  return value === null ? null : str(value, path)
}

export function parseWhoToCall(value: unknown, path: string): WhoToCall {
  const o = obj(value, path)
  return {
    person_id: str(o.person_id, `${path}.person_id`),
    name: str(o.name, `${path}.name`),
    why: str(o.why, `${path}.why`),
    degree: int(o.degree, `${path}.degree`, 1, 2),
    via: optStr(o.via, `${path}.via`),
    caution: optStr(o.caution, `${path}.caution`),
  }
}

function step(value: unknown, path: string): NetworkStep {
  const o = obj(value, path)
  return {
    from: str(o.from, `${path}.from`),
    to: str(o.to, `${path}.to`),
    to_id: str(o.to_id, `${path}.to_id`),
    kind: str(o.kind, `${path}.kind`),
    strength: int(o.strength, `${path}.strength`, 1, 5),
    context: str(o.context, `${path}.context`),
  }
}

function answer(value: unknown, path: string): NetworkAnswer {
  const o = obj(value, path)
  return {
    ...parseWhoToCall(value, path),
    headline: str(o.headline, `${path}.headline`),
    how: str(o.how, `${path}.how`),
    path: arr(o.path, `${path}.path`, step),
  }
}

export function parseNetworkPerson(value: unknown, path = 'person'): NetworkPerson {
  const o = obj(value, path)
  return {
    id: str(o.id, `${path}.id`),
    name: str(o.name, `${path}.name`),
    headline: str(o.headline, `${path}.headline`),
    location: str(o.location, `${path}.location`),
    degree: int(o.degree, `${path}.degree`, 1, 2),
    synthetic: bool(o.synthetic, `${path}.synthetic`),
    career: arr(o.career, `${path}.career`, str),
    schools: arr(o.schools, `${path}.schools`, str),
    how: str(o.how, `${path}.how`),
    path: arr(o.path, `${path}.path`, step),
    overlaps: arr(o.overlaps, `${path}.overlaps`, str),
    what_to_ask: arr(o.what_to_ask, `${path}.what_to_ask`, str),
  }
}

function networkCompany(value: unknown, path: string): NetworkCompany {
  const o = obj(value, path)
  return {
    symbol: str(o.symbol, `${path}.symbol`),
    company: str(o.company, `${path}.company`),
    sector: str(o.sector, `${path}.sector`),
    synthetic: bool(o.synthetic, `${path}.synthetic`),
    you_worked_there: arr(o.you_worked_there, `${path}.you_worked_there`, str),
    worked_there: arr(o.worked_there, `${path}.worked_there`, answer),
    best_placed: arr(o.best_placed, `${path}.best_placed`, answer),
  }
}

const KINDS: readonly NetworkKind[] = ['company', 'person', 'expertise', 'reconnect', 'help']

export function parseNetworkReply(value: unknown, path = 'reply'): NetworkReply {
  const o = obj(value, path)
  const kind = str(o.kind, `${path}.kind`)
  if (!KINDS.includes(kind as NetworkKind)) throw new ContractError(`${path}.kind`, KINDS.join(', '))
  return {
    question: str(o.question, `${path}.question`),
    kind: kind as NetworkKind,
    title: str(o.title, `${path}.title`),
    answers: arr(o.answers, `${path}.answers`, answer),
    ...(o.company === undefined ? {} : { company: networkCompany(o.company, `${path}.company`) }),
    ...(o.person === undefined ? {} : { person: parseNetworkPerson(o.person, `${path}.person`) }),
    ...(o.examples === undefined ? {} : { examples: arr(o.examples, `${path}.examples`, str) }),
  }
}

