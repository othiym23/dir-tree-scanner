FROM cgr.dev/chainguard/wolfi-base:latest

ARG USERNAME=ogd
ARG USER_UID=501
ARG USER_GID=20

# System packages: Rust toolchain, Node LTS, dev tools
RUN apk update && apk add --no-cache \
    rust-1.94 \
    uv \
    gh \
    just \
    nodejs-22 \
    npm \
    bun \
    neovim \
    git \
    openssh-client \
    openssh-keygen \
    build-base \
    glibc-dev \
    curl \
    bash \
    sudo \
    posix-libc-utils \
    && rm -rf /var/cache/apk/*

# Create user matching host UID/GID for NAS share access.
# GID 20 is 'staff' on macOS; create it if it doesn't exist.
RUN grep -q ":${USER_GID}:" /etc/group || addgroup -g ${USER_GID} staff && \
    GROUP_NAME=$(awk -F: -v gid=${USER_GID} '$3 == gid {print $1}' /etc/group) && \
    adduser -D -u ${USER_UID} -G "${GROUP_NAME}" -s /bin/bash ${USERNAME} && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME}

# Install npm-based tools globally
RUN npm install -g @anthropic-ai/claude-code prettier ccstatusline

# Install cargo-nextest as the user (goes into ~/.cargo/bin)
USER ${USERNAME}
RUN cargo install cargo-nextest --locked
USER root

ENV PATH="/home/${USERNAME}/.local/bin:/home/${USERNAME}/.cargo/bin:${PATH}"

# Pre-create directories that bind mounts will target so they're
# owned by the user, not root.  Docker creates missing mount targets
# as root, which blocks uv/cargo from writing siblings.
RUN mkdir -p /home/${USERNAME}/.local/share /home/${USERNAME}/.local/state \
             /home/${USERNAME}/.config && \
    chown -R ${USER_UID}:${USER_GID} /home/${USERNAME}/.local /home/${USERNAME}/.config

# ccstatusline config (used by the statusline shim inside the container)
COPY ccstatusline-settings.json /home/${USERNAME}/.config/ccstatusline/settings.json
RUN chown -R ${USER_UID}:${USER_GID} /home/${USERNAME}/.config/ccstatusline

# Install Python and dev tools via uv so they're ready before
# VS Code extensions start (avoids "Python not found" errors).
USER ${USERNAME}
RUN uv python install 3.14 && \
    ln -s python3.14 /home/${USERNAME}/.local/bin/python3 && \
    ln -s python3.14 /home/${USERNAME}/.local/bin/python && \
    uv tool install ruff && \
    uv tool install pyright && \
    uv tool install ty

WORKDIR /workspaces/euterpe-tools
