package com.ssafy.witw.analysis.service;

import com.ssafy.witw.analysis.repository.IssueCountryAnalysisResultRepository;
import com.ssafy.witw.analysis.repository.IssueCountryAnalysisTargetRepository.Target;
import com.ssafy.witw.analysis.service.IssueCountryAnalysisResponseValidator.AnalysisResult;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import javax.sql.DataSource;
import java.sql.Connection;
import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class IssueCountryAnalysisResultTransactionTest {
    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    static class TransactionConfig { }

    @Test
    void commits_both_writes_in_one_spring_transaction() throws Exception {
        verifyTransaction(false);
    }

    @Test
    void rolls_back_the_result_when_evidence_storage_fails() throws Exception {
        verifyTransaction(true);
    }

    private void verifyTransaction(boolean failEvidence) throws Exception {
        DataSource source = mock(DataSource.class);
        Connection connection = mock(Connection.class);
        when(source.getConnection()).thenReturn(connection);
        when(connection.getAutoCommit()).thenReturn(true);
        var repository = mock(IssueCountryAnalysisResultRepository.class);
        when(repository.insertAnalysis(anyLong(), anyString(), anyString(), anyString(), anyString(), anyLong(), any()))
                .thenAnswer(call -> {
                    assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isTrue();
                    assertThat(TransactionSynchronizationManager.hasResource(source)).isTrue();
                    return 123L;
                });
        doAnswer(call -> {
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isTrue();
            assertThat(TransactionSynchronizationManager.hasResource(source)).isTrue();
            if (failEvidence) throw new DataIntegrityViolationException("evidence foreign key");
            return null;
        }).when(repository).insertEvidence(123, List.of("a"));

        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(TransactionConfig.class, IssueCountryAnalysisResultService.class);
            context.registerBean(ObjectMapper.class, () -> JsonMapper.builder().build());
            context.registerBean(IssueCountryAnalysisResultRepository.class, () -> repository);
            context.registerBean("transactionManager", DataSourceTransactionManager.class,
                    () -> new DataSourceTransactionManager(source));
            context.refresh();
            var service = context.getBean(IssueCountryAnalysisResultService.class);
            var target = new Target(1, "issue", "KR", "Korea", 10);
            var result = new AnalysisResult("title", "summary", List.of("detail"));
            if (failEvidence) {
                assertThatThrownBy(() -> service.save(target, LocalDateTime.of(2026, 9, 18, 14, 0), result, List.of("a")))
                        .isInstanceOf(DataIntegrityViolationException.class);
                verify(connection).rollback();
                verify(connection, never()).commit();
            } else {
                service.save(target, LocalDateTime.of(2026, 9, 18, 14, 0), result, List.of("a"));
                verify(connection).commit();
                verify(connection, never()).rollback();
            }
            verify(repository).insertEvidence(123, List.of("a"));
            verify(source).getConnection();
            assertThat(TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
        }
    }
}
