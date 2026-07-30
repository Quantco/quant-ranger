from quant_ranger.site_config import (
    CommitAuthor,
    CopierMigration,
    PullRequestTemplate,
    PullRequestTemplates,
    SiteConfig,
)

site_config = SiteConfig(
    default_owner="octo-org",
    default_github_api_url="https://api.github.com",
    pixi_version_setup_pixi_marker="prefix-dev/setup-pixi",
    pull_request_templates=PullRequestTemplates(
        github_app_token=PullRequestTemplate(
            title="chore: Update GitHub App token inputs",
            body="Use the current inputs for GitHub App authentication.",
            branch_prefix="github-app-token-client-id",
        ),
        node_dependency_cooldown=PullRequestTemplate(
            title="chore: Add Node dependency safeguards",
            body="Configure minimum release ages for Node dependencies.",
            branch_prefix="node-dependency-cooldown-fixes",
        ),
        zizmor=PullRequestTemplate(
            title="chore: Fix GitHub Actions findings",
            body="Apply automated fixes to GitHub Actions workflows.",
            branch_prefix="zizmor-fixes",
        ),
    ),
    copier_migrations={
        "enable-example-feature": CopierMigration(
            answer_key="example_feature",
            templates=frozenset(
                {"github.com/quantco/copier-template-python-open-source"}
            ),
            resolve_desired_value=lambda _current_value: True,
            pull_request_template=PullRequestTemplate(
                title="chore: Enable the example feature",
                body="Enable the example Copier template feature.",
                branch_prefix="copier-migration",
            ),
        )
    },
    fallback_commit_author=CommitAuthor(
        name="example-ranger[bot]",
        email="1+example-ranger[bot]@users.noreply.github.com",
    ),
    copier_trusted_templates=frozenset(
        {"github.com/quantco/copier-template-python-open-source"}
    ),
)
