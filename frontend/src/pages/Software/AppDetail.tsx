import { EntityDetailPage } from './templates/EntityDetailPage'
import { appDomainConfig } from './configs/appConfig'

export default function AppDetail() {
  return <EntityDetailPage config={appDomainConfig} />
}
