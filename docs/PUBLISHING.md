# Publishing Pinpoint to the Nextcloud App Store

Nothing here has been done yet. Each step is public or hard to undo, so it waits for a go-ahead. The order
matters: the app id is registered with a certificate, and releases are signed with that certificate's key.

## 0. Before anything is public

- [ ] CI is green on `main` (`ci.yml`: Python, frontend, App Store metadata, release image, Nextcloud 33–35).
- [ ] `make eval` passes and `evals/results/` is current.
- [ ] Screenshots are current (`make screenshots`), each under 2 MiB if it's listed in `info.xml`.
- [ ] The Docker image works under HaRP, not only as manual-install (`dev/harp.sh`, then the integration
      tests minus the direct-port ones). Last checked on Nextcloud 35.0.3 with HaRP `release`.
- [ ] Decide the name. "Pinpoint" is free on the App Store (checked 2026-11-20), but Google's journalist
      tool and an AWS service use the same name. Renaming later means a new app id, so decide before step 2.

## 1. Public repository and image

```bash
gh repo create canakyildz/nextcloud-pinpoint --public --source . --push
```

The release workflow pushes the image to `ghcr.io/canakyildz/nextcloud-pinpoint`. After the first push, set
the package's visibility to **public** in GitHub (Packages → nextcloud-pinpoint → Package settings), or AppAPI
can't pull it.

## 2. Register the app id (certificate)

The App Store identifies an app by an id plus a certificate signed by Nextcloud.

```bash
mkdir -p ~/.nextcloud/certificates && cd ~/.nextcloud/certificates
openssl req -nodes -newkey rsa:4096 -keyout pinpoint.key -out pinpoint.csr -subj "/CN=pinpoint"
```

Keep `pinpoint.key` private and backed up. Losing it means re-registering, which deletes every earlier release.

Then open a pull request to [nextcloud/app-certificate-requests](https://github.com/nextcloud/app-certificate-requests)
that adds `pinpoint/pinpoint.csr`, using the repository's PR template in full. Their rules, as of November 2026:

- Every commit needs a `Signed-off-by:` line (DCO) that **you add yourself**, `git commit -s`. AI tools
  must never add it.
- Nextcloud's [AI contribution policy](https://github.com/nextcloud/.github/blob/master/AI_POLICY.md) asks
  you to tick the AI-disclosure checkbox and add an `Assisted-by:` trailer if an AI tool helped with the PR.
  This applies to PRs into Nextcloud's own repositories, not to this repository.
- Your email has to be visible on your GitHub profile.

Maintainers reply by committing `pinpoint/pinpoint.crt`. It usually takes 2–4 days. Save it next to the key.

## 3. Register the app on apps.nextcloud.com

Sign in at [apps.nextcloud.com](https://apps.nextcloud.com) with the account that will own the app, go to
*Developer → Register app*, paste the certificate, and the signature of the app id:

```bash
echo -n "pinpoint" | openssl dgst -sha512 -sign ~/.nextcloud/certificates/pinpoint.key | openssl base64
```

Then create an API token under *Account → API token*.

## 4. Release secrets in GitHub

In the repository's *Settings → Secrets and variables → Actions*:

| Secret | Value |
|---|---|
| `APP_PRIVATE_KEY` | contents of `pinpoint.key` |
| `APP_CERTIFICATE` | contents of `pinpoint.crt` (kept for code signing later) |
| `APPSTORE_TOKEN` | the apps.nextcloud.com API token |

## 5. Release

1. Move the `0.1.0 – unreleased` heading in `CHANGELOG.md` to the release date.
2. The version must match in `appinfo/info.xml` (`<version>` and `<image-tag>`), `pyproject.toml`,
   `package.json` and `ex_app/lib/pinpoint/__init__.py`. CI checks this.
3. Create the GitHub release with tag `v0.1.0`:

   ```bash
   gh release create v0.1.0 --title "Pinpoint 0.1.0" --notes-file CHANGELOG.md
   ```

`release.yml` then builds and pushes the multi-arch image (`linux/amd64`, `linux/arm64`), packages
`pinpoint.tar.gz` (`make appstore`: `appinfo/`, `img/`, licence, readme, changelog), attaches it to the
release, signs it and uploads it to the App Store. Without the secrets it stops after the tarball.

The same by hand, if needed:

```bash
make appstore
make sign    # prints the base64 signature of build/appstore/pinpoint.tar.gz
```

then *Developer → Upload release* on apps.nextcloud.com, with the release asset's download URL and the
signature.

## 6. After the release

- Install it from the App Store on a test instance with a HaRP daemon: *Apps → Pinpoint → Deploy and
  enable*. Check the Files action, the Pinpoint page, the Assistant task and the admin settings.
- AppAPI downloads the tarball, checks its signature against the certificate, and reads the routes from the
  signed `info.xml` (the App Store's own schema drops `<routes>`, which is expected).
- `max-version` in `info.xml` may be at most the latest Nextcloud major + 1. Raise it when Nextcloud 37 is
  out and the integration matrix passes on it.
