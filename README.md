# LogIndexer Pipeline
Logstash Log Indexer using pipeline to pipeline feature

## Contributing

The git repo contains following branches
- develop
- feature-* e.g. feature-apache_access, feature-aws_guard_duty
- release-* e.g. release-0.1.0
- stage
- master

You should not push directly to `develop`, `stage` or `master` branches. Changes to these branches should go via pull requests and should be reviewed.

### Developer Workflow:
Checkout a `feature-*` branch from `develop`, work on it and upon completion create a pull request to merge it to develop.
Review is required to merge it. After the `feature-*` gets merged to develop, it would get deployed to `dev` environment by `chef`.

After a few feature merges, we plan for release. We checkout `release-*` branch from the develop branch. To deploy this release to `stage` environment a PR should be created to `stage` branch. Issues and bugs should be worked upon by creating `hot-fix-*` branches from the `release-*` branch and should be merged to it after completion. Again PR should be created to merge the modified `release-*` branch to `stage` branch. This deploys the bug fixes when the PR gets merged.

To deploy to live environment create a PR to merge `release-*` branch to `master`.

### Config editing conventions

- tabsize should be 2 spaces
- EOL character should be \n (LF)

### CI/CD

Chef is being used for deployment. The recipies are listening to `develop` branch for deployment to `dev` and `master` branch for deployment to `prod` environment.

## Testing

Whenever a pr is created against develop branch drone is configured to test for syntax errors.
You can see the script in [.drone.yml](.drone.yml#L22) `test-config-on-pr` section.
