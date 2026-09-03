package com.ssafy.witw.domain.issue.dao;

import com.ssafy.witw.domain.issue.entity.Issue;
import org.springframework.data.jpa.repository.JpaRepository;

public interface IssueRepository extends JpaRepository<Issue, Long> {
}