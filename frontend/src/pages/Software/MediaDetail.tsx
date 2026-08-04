import { EntityDetailPage } from './templates/EntityDetailPage';
import { mediaDomainConfig } from './configs/mediaConfig';

export default function MediaDetail() {
  return <EntityDetailPage config={mediaDomainConfig} />;
}
