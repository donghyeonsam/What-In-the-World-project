package com.ssafy.witw.domain.article.controller;

import com.ssafy.witw.domain.article.service.ArticleNewsService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.time.LocalDate;
import java.time.LocalDateTime;

import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ArticleController.class)
@ActiveProfiles("test")
@AutoConfigureMockMvc(addFilters = false)
class ArticleTimeMachineControllerTest {
    @Autowired private MockMvc mvc;
    @MockitoBean private ArticleNewsService service;

    @Test
    void passesSelectedTimeToListDetailAndFilters() throws Exception {
        var selected = LocalDateTime.of(2025, 9, 16, 10, 50);
        String asOf = "2025-09-16T10:50:00+09:00";
        mvc.perform(get("/api/v1/articles").param("asOf", asOf)
                        .param("from", "2025-09-15").param("to", "2025-09-17"))
                .andExpect(status().isOk());
        verify(service).getArticles(null, null, null,
                LocalDate.of(2025, 9, 15), LocalDate.of(2025, 9, 17), 1, 12, selected);

        mvc.perform(get("/api/v1/articles/article-1").param("asOf", asOf))
                .andExpect(status().isOk());
        verify(service).getArticle("article-1", selected);

        mvc.perform(get("/api/v1/articles/filters").param("asOf", asOf))
                .andExpect(status().isOk());
        verify(service).getFilters(selected);
    }
}
