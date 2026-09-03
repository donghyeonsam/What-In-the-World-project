package com.ssafy.witw.domain.country.dao;

import com.ssafy.witw.domain.country.entity.Country;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CountryRepository extends JpaRepository<Country, String> {
}