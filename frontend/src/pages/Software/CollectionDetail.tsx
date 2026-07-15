import { EntityDetailPage } from './templates/EntityDetailPage'
import { gameDomainConfig } from './configs/gameConfig'

export default function CollectionDetail() {
  return <EntityDetailPage config={gameDomainConfig} />
}
