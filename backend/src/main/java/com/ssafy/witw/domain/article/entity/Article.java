package com.ssafy.witw.domain.article.entity;

import jakarta.persistence.*;
import org.springframework.context.annotation.Primary;

@Entity
public class Article {
    @Id()
    @GeneratedValue(strategy = GenerationType.AUTO)
    private Long id;
}
