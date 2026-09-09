package com.ssafy.witw.support;

import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.DockerImageName;

// 로컬은 Testcontainers 로 빈 DB 를 띄우고, CI 는 privileged = false 정책이라 Docker 가
// 없으므로 service 컨테이너를 TEST_POSTGRESQL_URL 로 받아 쓴다 (.gitlab/ci/be.yml).
public abstract class TestContainerSupport {

    private static final String POSTGRES_IMAGE = "postgres:17-alpine";
    private static final String VALKEY_IMAGE = "valkey/valkey:8-alpine";
    private static final int VALKEY_PORT = 6379;

    private static final String EXTERNAL_JDBC_URL = env("TEST_POSTGRESQL_URL", null);
    private static final boolean USE_CONTAINERS = EXTERNAL_JDBC_URL == null;

    private static PostgreSQLContainer postgres;
    private static GenericContainer<?> valkey;

    static {
        if (USE_CONTAINERS) {
            postgres = new PostgreSQLContainer(DockerImageName.parse(POSTGRES_IMAGE))
                    .withDatabaseName("witw");
            valkey = new GenericContainer<>(DockerImageName.parse(VALKEY_IMAGE))
                    .withExposedPorts(VALKEY_PORT);
            postgres.start();
            valkey.start();
        }
    }

    @DynamicPropertySource
    static void registerDatabaseProperties(DynamicPropertyRegistry registry) {
        if (USE_CONTAINERS) {
            registry.add("spring.datasource.url", postgres::getJdbcUrl);
            registry.add("spring.datasource.username", postgres::getUsername);
            registry.add("spring.datasource.password", postgres::getPassword);
            registry.add("spring.datasource.driver-class-name", postgres::getDriverClassName);

            registry.add("spring.data.redis.host", valkey::getHost);
            registry.add("spring.data.redis.port", () -> valkey.getMappedPort(VALKEY_PORT));
            return;
        }

        registry.add("spring.datasource.url", () -> EXTERNAL_JDBC_URL);
        registry.add("spring.datasource.username", () -> env("TEST_POSTGRESQL_USER", "postgres"));
        registry.add("spring.datasource.password", () -> env("TEST_POSTGRESQL_PASSWORD", ""));
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");

        registry.add("spring.data.redis.host", () -> env("TEST_VALKEY_HOST", "localhost"));
        registry.add("spring.data.redis.port", () -> env("TEST_VALKEY_PORT", "6379"));
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? fallback : value;
    }
}
