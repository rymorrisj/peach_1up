import { EntityListPage } from './templates/EntityListPage'
import { appDomainConfig } from './configs/appConfig'

export default function Apps() {
  return <EntityListPage config={appDomainConfig} />
}
