import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

import styles from './index.module.css';

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  // <Link to="..."> only auto-prepends baseUrl when `to` starts with '/'
  // (Link.js's shouldAddBaseUrlAutomatically), and that prepend step skips
  // adding baseUrl again whenever `to` already starts with the baseUrl
  // string (addBaseUrl's shouldAddBaseUrl guard). With baseUrl now '/docs/'
  // and the docs routeBasePath also 'docs', a leading-slash value like
  // '/docs/getting-started' collides with that guard and is left
  // un-prefixed, pointing at '/docs/getting-started' while the real route
  // (baseUrl + routeBasePath) is '/docs/docs/getting-started'. Same root
  // cause as the footer fix in docusaurus.config.ts. Resolving through
  // useBaseUrl() here with the leading slash dropped triggers baseUrl's
  // addition correctly (docs/getting-started does not start with baseUrl),
  // and the fully-resolved result is then safe to pass to <Link to>, which
  // will not double-prefix it.
  const gettingStartedUrl = useBaseUrl('docs/getting-started');
  const userGuideUrl = useBaseUrl('docs/user-guide');
  const contributorGuideUrl = useBaseUrl('docs/contributor-guide');
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to={gettingStartedUrl}>
            Getting Started
          </Link>
          <Link
            className="button button--secondary button--lg"
            to={userGuideUrl}>
            User Guide
          </Link>
          <Link
            className="button button--secondary button--lg"
            to={contributorGuideUrl}>
            Contributor Guide
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={siteConfig.title}
      description={siteConfig.tagline}>
      <HomepageHeader />
    </Layout>
  );
}
