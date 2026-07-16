import { EntityListPage } from './templates/EntityListPage'
import { gameDomainConfig } from './configs/gameConfig'

export default function Games() {
  return <EntityListPage config={gameDomainConfig} />
}
