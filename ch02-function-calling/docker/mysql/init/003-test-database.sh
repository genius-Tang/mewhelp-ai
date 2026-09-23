#!/usr/bin/env bash
set -Eeuo pipefail

export MYSQL_PWD="${MYSQL_ROOT_PASSWORD}"
mysql --protocol=socket -uroot <<SQL
CREATE DATABASE IF NOT EXISTS mewhelp_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON mewhelp_test.* TO '${MYSQL_USER}'@'%';
FLUSH PRIVILEGES;
SQL
mysql --protocol=socket -uroot mewhelp_test \
  < /docker-entrypoint-initdb.d/001-schema.sql
mysql --protocol=socket -uroot mewhelp_test \
  < /docker-entrypoint-initdb.d/002-seed.sql
unset MYSQL_PWD
