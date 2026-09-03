package com.ssafy.witw.domain.field.dao;

import com.ssafy.witw.domain.field.entity.Field;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FieldRepository extends JpaRepository<Field, Long> {
}