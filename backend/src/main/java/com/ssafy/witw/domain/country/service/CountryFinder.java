package com.ssafy.witw.domain.country.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.country.dao.CountryRepository;
import com.ssafy.witw.domain.country.entity.Country;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// 국가 조회·검증 단일 창구.
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class CountryFinder {

    private final CountryRepository countryRepository;

    public Country getCountry(String countryCode) {
        return countryRepository.findById(countryCode)
                .orElseThrow(() -> new GlobalException(ErrorCode.COUNTRY_NOT_FOUND));
    }
}
