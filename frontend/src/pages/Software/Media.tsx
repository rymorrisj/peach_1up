import { EntityListPage } from './templates/EntityListPage';
import { mediaDomainConfig } from './configs/mediaConfig';

export default function Media() {
  return <EntityListPage config={mediaDomainConfig} />;
}
