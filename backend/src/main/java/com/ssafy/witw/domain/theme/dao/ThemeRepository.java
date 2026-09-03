package com.ssafy.witw.domain.theme.dao;

import com.ssafy.witw.domain.theme.entity.Theme;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ThemeRepository extends JpaRepository<Theme, Long> {
}