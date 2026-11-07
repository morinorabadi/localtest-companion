# Trust boundaries and privacy

Localtest is a development convenience for sources and commands you trust.
The synced application, setup/start/stop commands, package installation scripts,
and registered actions run with your Ubuntu user permissions. Named-action
validation limits the command interface; it does not sandbox application code.
Do not connect it to untrusted source or expose it as a shared execution service.

The Ubuntu worker connects outbound through your existing authenticated Coder
SSH connection. No inbound Ubuntu listener or additional public port is opened.
The Coder broker and queue are accessible to that workspace's user. Anyone with
that account's access can submit the actions enabled for its connected profiles.
Choose unique profile names and use separate accounts/workspaces where needed.

The source mirror is one-way replica. Coder additions, modifications, and
deletions can overwrite/remove corresponding Ubuntu files. Registration rejects
nonempty/overlapping mirrors. Keep local state and personal files outside it.

`.env*` except example files, Git metadata, dependencies, and common build/state
paths are excluded. These patterns do not detect every secret: add project
ignores for private files with other names. Never put real keys in examples.

Ubuntu environment files are private local files and are not uploaded by sync.
However, command arguments and output are returned and recorded in the Coder
queue, and app logs may include sensitive values. Avoid secrets in arguments,
test output, HTTP response logging, or broad `env`/config-dump actions. Completed
results expire after seven days; that is not a guarantee of secure erasure.

Requests have bounded execution/output and run serially per project. Connection
loss during execution produces an unknown outcome and does not trigger automatic
replay. Inspect state before manually retrying a data-changing action.

Mutagen is downloaded from its official GitHub release over HTTPS and checked
against that release's SHA-256 manifest. Mutagen remains separately licensed;
see [its source and license](https://github.com/mutagen-io/mutagen).

To report a vulnerability, use this repository's private security reporting when
available. Otherwise contact the maintainer through their GitHub profile without
posting credentials, private app data, or a working exploit against a real user.
