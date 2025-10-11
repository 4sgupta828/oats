#!/usr/bin/env python3

import random
import sys
from typing import List, Tuple

# ANSI color codes
GREEN = '\033[92m'
YELLOW = '\033[93m'
GRAY = '\033[90m'
RESET = '\033[0m'
BOLD = '\033[1m'

class WordleGame:
    def __init__(self):
        self.word_list = [
            'APPLE', 'BEACH', 'CHAIR', 'DANCE', 'EAGLE', 'FLAME',
            'GRAPE', 'HOUSE', 'IMAGE', 'JUICE', 'KNIFE', 'LEMON',
            'MOUSE', 'NIGHT', 'OCEAN', 'PIANO', 'QUEEN', 'RIVER',
            'SNAKE', 'TABLE', 'UNCLE', 'VOICE', 'WATER', 'YOUTH'
        ]
        self.max_attempts = 6
        self.word_length = 5
        self.target_word = ''
    
    def new_game(self):
        """Start a new game by selecting a random word"""
        self.target_word = random.choice(self.word_list)
    
    def check_guess(self, guess: str) -> List[Tuple[str, str]]:
        """Check the guess against target word and return list of (letter, result)
        where result is 'correct', 'present', or 'absent'"""
        guess = guess.upper()
        result = []
        # Track which target letters have been matched to avoid double-counting
        used_positions = set()
        
        # First pass: Mark correct letters
        for i, (guess_letter, target_letter) in enumerate(zip(guess, self.target_word)):
            if guess_letter == target_letter:
                result.append((guess_letter, 'correct'))
                used_positions.add(i)
            else:
                result.append((guess_letter, None))
        
        # Second pass: Mark present letters (in wrong position)
        for i, (guess_letter, status) in enumerate(result):
            if status is None:  # Skip already marked correct letters
                # Check if letter exists in target word in an unused position
                found = False
                for j, target_letter in enumerate(self.target_word):
                    if j not in used_positions and guess_letter == target_letter:
                        result[i] = (guess_letter, 'present')
                        used_positions.add(j)
                        found = True
                        break
                if not found:
                    result[i] = (guess_letter, 'absent')
        
        return result

    def display_result(self, result: List[Tuple[str, str]]):
        """Display the guess result with colors"""
        display = ''
        for letter, status in result:
            if status == 'correct':
                display += f'{GREEN}{letter}{RESET}'
            elif status == 'present':
                display += f'{YELLOW}{letter}{RESET}'
            else:  # absent
                display += f'{GRAY}{letter}{RESET}'
        print(display)

    def play(self):
        """Main game loop"""
        print(f'{BOLD}Welcome to Wordle!{RESET}')
        print(f'Try to guess the {self.word_length}-letter word in {self.max_attempts} attempts.')
        
        attempts = 0
        won = False
        
        while attempts < self.max_attempts and not won:
            attempts += 1
            print(f'\nAttempt {attempts}/{self.max_attempts}')
            
            # Get valid input
            while True:
                guess = input('Enter your guess: ').strip().upper()
                if len(guess) != self.word_length:
                    print(f'Please enter a {self.word_length}-letter word')
                    continue
                if not guess.isalpha():
                    print('Please enter only letters')
                    continue
                break
            
            # Check guess and display result
            result = self.check_guess(guess)
            self.display_result(result)
            
            # Check for win
            if all(status == 'correct' for _, status in result):
                won = True
                print(f'\n{GREEN}Congratulations! You won in {attempts} attempts!{RESET}')
                break
        
        if not won:
            print(f'\n{GRAY}Game Over! The word was {BOLD}{self.target_word}{RESET}')

def main():
    game = WordleGame()
    game.new_game()
    game.play()

if __name__ == '__main__':
    main()
