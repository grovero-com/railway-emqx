FROM docker.io/library/emqx:5
#TODO(sm): include TLS certificates

COPY emqx.conf /opt/emqx/etc/emqx.conf
COPY acl.conf /opt/emqx/etc/

COPY docker-entrypoint.sh /usr/bin/
COPY docker-healthcheck /usr/local/bin/

HEALTHCHECK CMD ["docker-healthcheck"]

# ENTRYPOINT ["/usr/bin/env", "bash", "-c", "( sleep 10; docker-healthcheck ) & /usr/bin/docker-entrypoint.sh"]
ENTRYPOINT ["/usr/bin/docker-entrypoint.sh"]
CMD ["/opt/emqx/bin/emqx", "foreground"]
